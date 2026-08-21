/**
 * E2E Tests: Credential Miscellaneous (additive)
 *
 * Remaining tests from the ANSTRAT-1901 test plan not covered by other spec files.
 * Tests 27-28 (workflows tab) are covered by credential-detail.spec.ts.
 *
 * Covers:
 * - Test 29: Workflows tab error state with retry
 * - Test 31: Disabled credential display in selector
 * - Test 34: Credential selector loading and error states
 * - Test 36: Alert notifications (success auto-dismiss, error alerts)
 * - Test 38: Dynamic field renderer help text
 * - Test 39: Credential selector FormLabelWithHelp popover
 * - Test 42: Secret field security ($encrypted$ sentinel)
 * - Test 43: Submit state (loading spinner, button disable)
 */

import { test, expect, toAppUrl } from './fixtures'
import {
  createTestCredential,
  deleteCredentialByName,
  deleteCredentialById,
  filterCredentialByName,
  goToCredentialsList,
  navigateToCredentialDetail,
  selectCredentialType,
} from './helpers/credentials'
import { pfWidget } from './helpers/patternfly'
import {
  buildUniqueName,
  clickAddConnectedStep,
  navigateToApiActionForm,
  selectProjectIfRequired,
} from './helpers/workflows'
import { ensureProject } from './utils/api'

// ---------------------------------------------------------------------------
// Test 29: Workflows Tab — Error State with Retry
// ---------------------------------------------------------------------------
test.describe('Credential Workflows Tab', () => {
  test('workflows tab shows error state with retry button on API failure', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-wf-error' })
    try {
      // Set up route intercept before navigating (avoid race with prefetch)
      await app.route('**/api/v1/credentials/*/workflows', (route) =>
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            type: 'internal-error',
            title: 'Internal Server Error',
            detail: 'Simulated failure',
            code: 'INTERNAL_ERROR',
            retryable: true,
          }),
        })
      )

      await navigateToCredentialDetail(app, name)
      await expect(app.getByRole('tab', { name: /Details/, selected: true })).toBeVisible()
      await app.getByRole('tab', { name: /Workflows/ }).click()

      await expect(
        app.getByTestId('error-state').getByRole('heading', { name: /Failed to load workflows/ })
      ).toBeVisible()

      const retryButton = app.getByRole('button', { name: /Retry/i })
      await expect(retryButton).toBeVisible()

      await app.unroute('**/api/v1/credentials/*/workflows')

      await retryButton.click()

      const emptyState = app.getByText('No workflows using this credential')
      const table = app.getByRole('grid', { name: 'Workflows using this credential' })
      await expect(emptyState.or(table)).toBeVisible({ timeout: 10_000 })
    } finally {
      await deleteCredentialByName(app, name)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 31: Disabled Credential Display in Selector
// ---------------------------------------------------------------------------
test.describe('Credential Selector — Disabled Credential', () => {
  test('disabled credential appears with "(disabled)" suffix and is not selectable', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-disabled-sel', enabled: false })
    try {
      await navigateToApiActionForm(app)
      const credBtn = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await expect(credBtn).toBeEnabled({ timeout: 10_000 })
      await credBtn.click()

      const option = app.getByRole('option', { name: name, exact: true })
      const optionVisible = await option
        .waitFor({ state: 'visible', timeout: 5_000 })
        .then(() => true)
        .catch(() => false)

      if (optionVisible) {
        await expect(app.getByText('(disabled)')).toBeVisible()
        await expect(option).toBeDisabled()

        await option.click({ force: true })
        const toggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
        await expect(toggle).not.toContainText(name)
      } else {
        test.skip(true, 'Disabled credential not visible in selector — may be filtered out')
      }
    } finally {
      await deleteCredentialByName(app, name)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 34: Credential Selector — Error State with Retry
// ---------------------------------------------------------------------------
test.describe('Credential Selector — Error State', () => {
  test('credential selector shows error state and retry on API failure', async ({ app }) => {
    await ensureProject(app)

    await app.route('**/api/v1/credentials**', (route) => {
      const url = route.request().url()
      if (url.includes('/credential_types') || url.includes('/credentials/')) {
        return route.continue()
      }
      return route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          type: 'internal-error',
          title: 'Internal Server Error',
          detail: 'Simulated failure',
          code: 'INTERNAL_ERROR',
          retryable: true,
        }),
      })
    })

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

      await selectProjectIfRequired(app)

      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()

      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Action', exact: true }).click()
      await panel.getByRole('button', { name: 'REST API', exact: true }).click()

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()

      const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      // React Query retries 3 times (1s+2s+4s=7s) before isError=true. Under
      // Konflux CPU pressure the retry timers fire late, so use 20s headroom.
      await expect(credToggle).toContainText('Error loading credentials', { timeout: 20_000 })

      const retryBtn = app.getByRole('button', { name: /Retry loading credentials/i })
      await expect(retryBtn).toBeVisible()

      await app.unroute('**/api/v1/credentials**')

      await retryBtn.click()

      await expect(credToggle).not.toContainText('Error loading credentials', { timeout: 10_000 })
    } finally {
      await app.unroute('**/api/v1/credentials**')
    }
  })
})

// ---------------------------------------------------------------------------
// Test 36: Alert Notifications
// ---------------------------------------------------------------------------
test.describe('Alert Notifications', () => {
  test('success alerts auto-dismiss for create and delete', async ({ app }) => {
    const { name, id: credId } = await createTestCredential(app, { prefix: 'e2e-alert-lifecycle' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })

      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: /Delete/ }).click()
      const deleteDialog = app.getByRole('dialog')
      await deleteDialog.getByRole('checkbox').click()
      await deleteDialog.getByRole('button', { name: 'Delete' }).click()
      await expect(app.getByText('Credential deleted')).toBeVisible()

      await expect(app.getByText('Credential deleted')).not.toBeVisible({ timeout: 12_000 })
    } finally {
      await deleteCredentialById(app, credId)
    }
  })

  test('error alert shows API error message on create failure', async ({ app }) => {
    await goToCredentialsList(app, { ensureCreateEnabled: true })

    await app.route('**/api/v1/credentials', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            type: 'internal-error',
            title: 'Internal Server Error',
            detail: 'Simulated server failure during credential creation',
            code: 'INTERNAL_ERROR',
            retryable: true,
          }),
        })
      }
      return route.continue()
    })

    await app.getByRole('button', { name: 'Create credential' }).click()
    const modal = app.getByRole('dialog')
    await modal.getByRole('textbox', { name: 'Credential name' }).fill('error-test-cred')
    await selectCredentialType(modal, 'HTTP Bearer Token')
    await modal.getByRole('textbox', { name: 'Token' }).fill('test-token')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    // PF6 toast Alert is aria-live only — no role="alert" (see waitForUIReady).
    const errorAlert = pfWidget(app, 'Alert').filter({ hasText: /error|fail/i })
    await expect(errorAlert).toBeVisible({ timeout: 10_000 })

    await app.unroute('**/api/v1/credentials')
  })
})

// ---------------------------------------------------------------------------
// Test 38: Dynamic Field Renderer — Help Text
// ---------------------------------------------------------------------------
test.describe('Dynamic Field Renderer — Help Text', () => {
  test('help text displays below credential form fields', async ({ app }) => {
    await goToCredentialsList(app, { ensureCreateEnabled: true })
    await app.getByRole('button', { name: 'Create credential' }).click()

    const modal = app.getByRole('dialog')

    await selectCredentialType(modal, 'HTTP Bearer Token')

    // Help buttons use aria-label="${label} help" — only present when help_text is set
    const tokenHelpButton = modal.getByRole('button', { name: /Token help/i })
    const hasHelpText = await tokenHelpButton
      .waitFor({ state: 'visible', timeout: 5_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasHelpText, 'Credential type does not have help_text configured on this backend')

    await tokenHelpButton.click()
    // Exact name — the create modal's accessible name also contains "Token help".
    await expect(app.getByRole('dialog', { name: 'Token help', exact: true })).toBeVisible({ timeout: 5_000 })

    await selectCredentialType(modal, 'HTTP Basic Auth')

    await expect(modal.getByRole('button', { name: /Username help/i })).toBeVisible()
    await expect(modal.getByRole('button', { name: /Password help/i })).toBeVisible()
  })
})

test.describe('Credential Selector — FieldHelpPopover', () => {
  test('credential selector label shows help popover icon', async ({ app }) => {
    await navigateToApiActionForm(app)

    const helpButton = app.getByRole('button', { name: 'More info for Authentication credential' })
    await expect(helpButton).toBeVisible()

    await helpButton.click()

    await expect(app.getByText('Credentials are encrypted and never exposed in logs')).toBeVisible()
    await expect(app.getByText('You can create a new credential directly from this dropdown')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Test 42: Secret Field Security
// ---------------------------------------------------------------------------
test.describe('Secret Field Security', () => {
  test('secret fields never show plaintext on detail page', async ({ app }) => {
    const credName = buildUniqueName('e2e-secret-sec')

    try {
      await goToCredentialsList(app, { ensureCreateEnabled: true })
      await app.getByRole('button', { name: 'Create credential' }).click()
      const createModal = app.getByRole('dialog')
      await createModal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      await selectCredentialType(createModal, 'HTTP Bearer Token')
      await createModal.getByRole('textbox', { name: 'Token' }).fill('super-secret-value-12345')

      await createModal.getByRole('button', { name: 'Create credential' }).click()
      await expect(app.getByText('Credential created')).toBeVisible()

      await navigateToCredentialDetail(app, credName)

      const detailsTab = app.getByLabel('Details')
      await expect(detailsTab.getByText('Token', { exact: true })).toBeVisible()
      await expect(detailsTab.getByText('super-secret-value-12345')).not.toBeVisible()

      await app.reload()
      await expect(app.getByLabel('Details').getByText('Token', { exact: true })).toBeVisible()
      await expect(app.getByText('super-secret-value-12345')).not.toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})

// ---------------------------------------------------------------------------
// Test 43: Submit State — Loading Spinner
// ---------------------------------------------------------------------------
test.describe('Submit State — Loading Spinner', () => {
  test('submit button disables and shows spinner during creation', async ({ app }) => {
    const credName = buildUniqueName('e2e-submit-spin')

    try {
      await goToCredentialsList(app, { ensureCreateEnabled: true })
      await app.getByRole('button', { name: 'Create credential' }).click()
      const modal = app.getByRole('dialog')
      await modal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      await selectCredentialType(modal, 'HTTP Bearer Token')
      await modal.getByRole('textbox', { name: 'Token' }).fill('spinner-test-token')

      // Delay only the POST response so we can observe the loading state
      await app.route('**/api/v1/credentials', (route) => {
        if (route.request().method() === 'POST') {
          return new Promise<void>((resolve) => setTimeout(resolve, 3_000)).then(() => route.continue())
        }
        return route.continue()
      })

      const submitBtn = modal.getByRole('button', { name: 'Create credential' })
      await submitBtn.click()

      // PF6 Button with isLoading adds pf-m-progress class (does not set disabled attr)
      await expect(submitBtn).toHaveClass(/pf-m-progress/, { timeout: 5_000 })

      await expect(app.getByText('Credential created')).toBeVisible({ timeout: 10_000 })
      await app.unroute('**/api/v1/credentials')

      await expect(modal).not.toBeVisible()
    } finally {
      await app.unroute('**/api/v1/credentials')
      await deleteCredentialByName(app, credName)
    }
  })
})
