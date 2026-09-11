import { type Locator, type Response } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import {
  apiRequest,
  createCredentialViaApi,
  deleteCredentialViaApi,
  ensureProject,
  listCredentialsByName,
} from '../utils/api'

import { buildUniqueName, selectFirstProject } from './workflows'

/**
 * Select a credential type from the PF6 Select dropdown.
 *
 * The credential type field uses a PF6 `Select` component (button toggle +
 * dropdown menu) instead of a native `<select>`. Interaction requires
 * clicking the toggle button to open the menu, then clicking the desired
 * option. The menu is portaled to the document body (PatternFly default),
 * so options are queried from the page rather than the modal container.
 */
export async function selectCredentialType(container: Locator, typeName: string): Promise<void> {
  const page = container.page()
  await container.getByRole('button', { name: 'Credential type', exact: true }).click()
  const option = page.getByRole('option', { name: typeName, exact: true })
  await option.waitFor({ state: 'visible', timeout: 10_000 })
  await option.click()
}

/** Open the Create Credential modal and return the dialog locator. */
export async function openCreateModal(app: Page) {
  await goToCredentialsList(app, { ensureCreateEnabled: true })
  await app.getByRole('button', { name: 'Create credential' }).first().click()
  const modal = app.getByRole('dialog')
  await expect(modal).toBeVisible()
  return modal
}

/** Navigate to the credentials list page and wait for it to load */
export async function goToCredentialsList(app: Page, options?: { ensureCreateEnabled?: boolean }) {
  if (options?.ensureCreateEnabled) {
    await ensureProject(app)
  }

  await app.goto(toAppUrl('/configuration/credentials'))
  await expect(app.getByText('Credentials', { exact: true }).first()).toBeVisible({ timeout: 20_000 })

  if (!options?.ensureCreateEnabled) return

  const createBtn = app.getByRole('button', { name: 'Create credential' }).first()
  await createBtn.waitFor({ state: 'visible', timeout: 10_000 })

  // Select a project so the Create Credential modal's Project field is pre-populated
  await selectFirstProject(app)
}

/**
 * Create a test credential — tries UI first, falls back to API.
 * Returns { name, id } for cleanup.
 */
export async function createTestCredential(
  app: Page,
  options: { prefix?: string; enabled?: boolean } = {}
): Promise<{ name: string; id: string | null }> {
  const name = buildUniqueName(options.prefix ?? 'e2e-cred')

  const project = await ensureProject(app)
  if (project) {
    const credId = await createCredentialViaApi(app, { name, projectId: project.id })
    if (credId) {
      if (options.enabled === false) {
        const resp = await apiRequest(app, 'patch', `/credentials/${credId}`, {
          data: { enabled: false },
        })
        if (!resp.ok()) {
          await disableCredential(app, name)
        }
      }
      return { name, id: credId }
    }
  }

  const uiCreated = await createTestCredentialViaUi(app, name)
  if (!uiCreated) {
    throw new Error(`Cannot create credential "${name}" via API or UI`)
  }

  if (options.enabled === false) {
    await disableCredential(app, name)
  }
  return { name, id: null }
}

async function createTestCredentialViaUi(app: Page, name: string): Promise<boolean> {
  try {
    await goToCredentialsList(app, { ensureCreateEnabled: true })
    await app.getByRole('button', { name: 'Create credential' }).first().click()

    const modal = app.getByRole('dialog')
    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'HTTP Bearer Token')
    await modal.getByRole('textbox', { name: 'Token' }).fill('e2e-test-token')
    await modal.getByRole('button', { name: 'Create credential' }).click()
    await expect(app.getByText('Credential created')).toBeVisible()
    return true
  } catch {
    return false
  }
}

/** Per-attempt budget for the enable/disable PATCH to come back. */
const CREDENTIAL_PATCH_TIMEOUT = 20_000

/** The PATCH that the Enabled switch issues (`PATCH /api/v1/credentials/{id}`). */
export function isCredentialPatchResponse(response: Response): boolean {
  return (
    response.request().method() === 'PATCH' && /\/api\/v1\/credentials\/[^/]+$/.test(new URL(response.url()).pathname)
  )
}

/** Wait until the usage checks finish so the Disable action is actually clickable. */
export async function waitForDisableDialogReady(dialog: Locator, credentialName?: string): Promise<void> {
  await expect(dialog.getByText('Disable credential?')).toBeVisible()
  // The spinner only clears once the affected-workflows and affected-integrations
  // API calls both resolve — give it extra time under CI load
  await expect(dialog.getByText(/Checking for workflows and integrations/)).toHaveCount(0, {
    timeout: 25_000,
  })
  if (credentialName) {
    await expect(dialog.getByText(new RegExp(credentialName))).toBeVisible()
  }
  await expect(dialog.getByRole('button', { name: 'Disable' })).toBeEnabled()
}

/** Per-attempt budget for landing the Enabled switch click. */
const DISABLE_TOGGLE_CLICK_TIMEOUT = 5_000
/** Per-attempt budget for the confirmation dialog to appear after the click. */
const DISABLE_DIALOG_TIMEOUT = 5_000
/** Total budget for getting the confirmation dialog open. */
const DISABLE_DIALOG_RETRY_TIMEOUT = 30_000

/**
 * Flip a credential's Enabled switch from its list row and return the disable
 * confirmation dialog, ready to act on.
 *
 * PatternFly's `Switch` hides its `<input>` behind a styled span, so every caller
 * has to click it with `force: true` — which skips the actionability wait
 * entirely, including the stability check that would otherwise have held the
 * click until the row stopped moving. The row is re-rendered whenever the
 * credentials query resolves, and `filterCredentialByName` returns as soon as it
 * has pressed *Apply filter*, without waiting for the filtered page to land. A
 * forced click inside that window hits a row React is replacing: no `onChange`
 * runs, no dialog opens, and the caller fails up to 25s later inside
 * `waitForDisableDialogReady` on a dialog that was never there.
 *
 * Re-opening on a miss is the same remedy `triggerVerifyWorkflow` uses for the
 * builder kebab. The click is skipped whenever the dialog is already up, so a
 * slow open is waited out rather than toggled back — `openDisableDialog` is
 * idempotent, but a second forced click would land on the modal backdrop.
 */
export async function openDisableDialogFromRow(app: Page, row: Locator, credentialName?: string): Promise<Locator> {
  const dialog = app.getByRole('dialog')
  const title = dialog.getByText('Disable credential?')

  await expect(async () => {
    if (!(await title.isVisible().catch(() => false))) {
      await expect(row).toBeVisible({ timeout: DISABLE_TOGGLE_CLICK_TIMEOUT })
      // Swallow the click failure: Playwright retries a click on its own when the
      // element detaches, so an unbounded one would sit inside a single attempt
      // for the whole retry budget instead of letting `toPass` start over.
      await row
        .getByRole('switch')
        .click({ force: true, timeout: DISABLE_TOGGLE_CLICK_TIMEOUT })
        .catch(() => {})
    }
    await expect(title).toBeVisible({ timeout: DISABLE_DIALOG_TIMEOUT })
  }).toPass({ timeout: DISABLE_DIALOG_RETRY_TIMEOUT, intervals: [500, 1_000, 2_000] })

  await waitForDisableDialogReady(dialog, credentialName)
  return dialog
}

/**
 * Flip a credential's Enabled switch off from its list row, returning once the
 * server has recorded it.
 *
 * The switch is driven by `useOptimisticCredentialEnabled`, a correct React 19
 * `useOptimistic` + `startTransition` Action: it flips the UI *before* the PATCH
 * is issued and rolls back on failure. So `not.toBeChecked()` is satisfied by
 * optimistic state alone, and any navigation that follows tears the document
 * down mid-request — the server never records the change, and because
 * `queryClient` sets no `staleTime` the return trip refetches and renders the
 * credential still enabled.
 *
 * The response wait is armed immediately before the Disable click, not before
 * the toggle click: between the two sits the affected-workflows and
 * affected-integrations usage check, which is budgeted 25s on its own and would
 * otherwise consume most of this wait.
 */
export async function disableCredentialFromRow(app: Page, row: Locator): Promise<void> {
  const dialog = await openDisableDialogFromRow(app, row)

  const patchDone = app.waitForResponse(isCredentialPatchResponse, { timeout: CREDENTIAL_PATCH_TIMEOUT })
  await dialog.getByRole('button', { name: 'Disable' }).click()

  const response = await patchDone
  expect(response.ok(), `PATCH /credentials returned ${response.status()}`).toBe(true)
  await expect(dialog).not.toBeVisible()
  await expect(row.getByRole('switch')).not.toBeChecked()
}

async function disableCredential(app: Page, name: string): Promise<void> {
  await goToCredentialsList(app)
  await filterCredentialByName(app, name)
  await disableCredentialFromRow(app, app.getByRole('row', { name: new RegExp(name) }))
}

/**
 * Delete a credential by name via the authenticated API (best-effort cleanup).
 */
export async function deleteCredentialByName(app: Page, name: string) {
  if (app.isClosed()) return
  try {
    const credentials = await listCredentialsByName(app, name)
    for (const cred of credentials) {
      await deleteCredentialViaApi(app, cred.id)
    }
  } catch {
    // Best-effort cleanup
  }
}

/**
 * Delete a credential by ID via the API (best-effort cleanup).
 */
export async function deleteCredentialById(app: Page, credentialId: string | null) {
  if (!credentialId || app.isClosed()) return
  await deleteCredentialViaApi(app, credentialId)
}

/**
 * Create a credential of any type via the UI.
 * Navigates to credentials list, opens create modal, fills fields, and submits.
 */
export async function createCredentialOfTypeViaUI(
  app: Page,
  options: {
    name: string
    type: string
    fields: Record<string, string>
  }
) {
  await goToCredentialsList(app, { ensureCreateEnabled: true })
  await app.getByRole('button', { name: 'Create credential' }).first().click()

  const modal = app.getByRole('dialog')
  await modal.getByRole('textbox', { name: 'Credential name' }).fill(options.name)
  await selectCredentialType(modal, options.type)

  for (const [fieldName, value] of Object.entries(options.fields)) {
    await modal.getByRole('textbox', { name: fieldName }).fill(value)
  }

  await modal.getByRole('button', { name: 'Create credential' }).click()
  await expect(app.getByText('Credential created')).toBeVisible()
}

/** Check if a response is a successful credentials API request (excludes credential_types). */
export const isCredentialsResponse = (resp: Response) =>
  resp.url().includes('/credentials') &&
  !resp.url().includes('/credential_types') &&
  resp.url().includes('for_action=use') &&
  resp.status() === 200

/** Filter the credentials list by keyword. */
export async function filterCredentialByName(app: Page, name: string) {
  await app.getByPlaceholder('Filter by keyword').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

/**
 * Navigate to credentials list, filter by name, and click the credential name
 * link to open its detail page.
 */
export async function navigateToCredentialDetail(app: Page, credentialName: string) {
  await goToCredentialsList(app)

  await app.getByPlaceholder('Filter by keyword').fill(credentialName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const table = app.getByRole('grid', { name: 'Credentials table' })
  await table.getByRole('link', { name: credentialName, exact: true }).click()
  await expect(app).toHaveURL(/configuration\/credentials\//)
  // Wait for the credential data to load — confirms the detail API responded
  await expect(app.locator('h1').filter({ hasText: credentialName })).toBeVisible({ timeout: 15_000 })
}
