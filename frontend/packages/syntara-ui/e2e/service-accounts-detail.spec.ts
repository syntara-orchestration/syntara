/**
 * E2E Tests: Service Accounts — Detail Pages
 *
 * Test cases covered:
 * - UI-5: Detail page — view and edit
 * - UI-6: Detail page — disable/enable toggle
 * - UI-7: Delete with confirmation
 * - UI-14: No group membership option
 */
import { test, expect } from './fixtures'
import {
  createTestServiceAccount,
  deleteServiceAccountViaApi,
  goToServiceAccountDetail,
} from './helpers/service-accounts'
import { buildUniqueName } from './helpers/workflows'

test.describe('UI-5: Service Account Detail — View and Edit', () => {
  let sa: { id: string; name: string }
  const prefix = buildUniqueName('sa-detail')

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sa = await createTestServiceAccount(page, { prefix })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      await deleteServiceAccountViaApi(page, sa.id)
    } finally {
      await page.close()
    }
  })

  test('displays detail page with correct tabs and fields', async ({ app }) => {
    await goToServiceAccountDetail(app, sa)

    await expect(app.getByRole('tab', { name: 'Details' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Credentials' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Assignments' })).toBeVisible()

    const details = app.getByRole('tabpanel', { name: 'Details' })
    await expect(details.getByText('Name')).toBeVisible()
    await expect(details.getByText('Owning project')).toBeVisible()
    await expect(details.getByText('Description')).toBeVisible()
    await expect(details.getByText('State')).toBeVisible()
    await expect(details.getByText('Created')).toBeVisible()
    await expect(details.getByText('Last authenticated')).toBeVisible()
  })

  test('edits name and description via edit modal', async ({ app }) => {
    await goToServiceAccountDetail(app, sa)

    await app.getByRole('button', { name: 'Edit service account' }).click()

    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()
    await expect(modal.getByText(`Edit ${sa.name}`)).toBeVisible()

    const nameInput = modal.getByRole('textbox', { name: 'Name', exact: true })
    await expect(nameInput).toHaveValue(sa.name)

    const newName = buildUniqueName('sa-edited')
    await nameInput.clear()
    await nameInput.fill(newName)
    await modal.getByRole('textbox', { name: 'Description', exact: true }).fill('Updated description')

    await modal.getByRole('button', { name: 'Save service account' }).click()

    await expect(app.getByText('Service account updated')).toBeVisible()
    await expect(app.getByRole('heading', { level: 1, name: newName })).toBeVisible()

    // Update sa.name so afterAll cleanup still works (cleanup uses ID, not name)
    sa = { ...sa, name: newName }
  })
})

test.describe('UI-6: Service Account Detail — Disable/Enable Toggle', () => {
  test('disables with confirmation dialog and re-enables without dialog', async ({ app }) => {
    // Create inside the test so CI retries get a fresh active SA (beforeAll is not
    // re-run on retry, which left a disabled SA and compounded flakes).
    const sa = await createTestServiceAccount(app, { prefix: 'sa-toggle' })
    try {
      await goToServiceAccountDetail(app, sa)

      const toggle = app.getByRole('switch', { name: 'Toggle service account status' })
      // useCanI is safe-false until resolved — wait until the switch is enabled so
      // onChange is live before we click (previously raced and never opened the dialog).
      await expect(toggle).toBeEnabled()
      await expect(toggle).toBeChecked()

      // PF Switch hides the real <input>; Playwright's force-click on a hidden/clipped
      // element doesn't reliably fire the change event. Native click() always works.
      await toggle.evaluate((el: HTMLElement) => el.click())

      const dialog = app.getByRole('dialog')
      await expect(dialog.getByText('Disable service account?')).toBeVisible()
      await expect(dialog.getByText(sa.name)).toBeVisible()
      await dialog.getByRole('button', { name: 'Disable service account' }).click()

      await expect(toggle).not.toBeChecked({ timeout: 10_000 })

      await expect(dialog).not.toBeVisible()
      await expect(toggle).toBeEnabled()
      await toggle.evaluate((el: HTMLElement) => el.click())

      await expect(toggle).toBeChecked({ timeout: 10_000 })
    } finally {
      await deleteServiceAccountViaApi(app, sa.id)
    }
  })
})

test.describe('UI-7: Service Account Detail — Delete with Confirmation', () => {
  test('delete button is disabled until acknowledgement checkbox is checked', async ({ app }) => {
    const sa = await createTestServiceAccount(app, { prefix: 'sa-del-ack' })
    try {
      await goToServiceAccountDetail(app, sa)

      await app.getByRole('button', { name: 'Service account actions' }).click()
      await app.getByRole('menuitem', { name: 'Delete service account' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog.getByText('Delete service account?')).toBeVisible()
      await expect(dialog.getByText(sa.name)).toBeVisible()

      const deleteButton = dialog.getByRole('button', { name: 'Delete service account' })
      await expect(deleteButton).toBeDisabled()

      await dialog
        .getByRole('checkbox', {
          name: 'I understand this service account will be permanently deleted and all OAuth tokens revoked.',
        })
        .check()

      await expect(deleteButton).toBeEnabled()

      // Cancel instead of deleting — cleanup via afterAll isn't needed if we cancel
      await dialog.getByRole('button', { name: 'Cancel' }).click()
    } finally {
      await deleteServiceAccountViaApi(app, sa.id)
    }
  })

  test('deletes service account and redirects to list', async ({ app }) => {
    const sa = await createTestServiceAccount(app, { prefix: 'sa-del-confirm' })

    await goToServiceAccountDetail(app, sa)

    await app.getByRole('button', { name: 'Service account actions' }).click()
    await app.getByRole('menuitem', { name: 'Delete service account' }).click()

    const dialog = app.getByRole('dialog')
    await dialog
      .getByRole('checkbox', {
        name: 'I understand this service account will be permanently deleted and all OAuth tokens revoked.',
      })
      .check()

    await dialog.getByRole('button', { name: 'Delete service account' }).click()

    // Redirect only fires on successful deletion (onSuccess callback)
    await app.waitForURL(/\/service-accounts$/)
    await expect(app.getByRole('tab', { name: 'Service accounts', exact: true })).toBeVisible()

    // Wait for list data to load, then verify SA is gone
    const emptyState = app.getByText('No service accounts yet')
    const filterInput = app.getByPlaceholder('Filter by name')
    await expect(emptyState.or(filterInput)).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('link', { name: sa.name })).toHaveCount(0)
  })
})

test.describe('UI-14: Service Account Detail — No Group Membership', () => {
  let sa: { id: string; name: string }

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sa = await createTestServiceAccount(page, { prefix: 'sa-no-groups' })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      await deleteServiceAccountViaApi(page, sa.id)
    } finally {
      await page.close()
    }
  })

  test('service account detail page has no Groups tab', async ({ app }) => {
    await goToServiceAccountDetail(app, sa)

    // Verify the expected tabs exist
    await expect(app.getByRole('tab', { name: 'Details' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Credentials' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Assignments' })).toBeVisible()

    // Verify Groups tab does NOT exist
    await expect(app.getByRole('tab', { name: /Groups/i })).toHaveCount(0)
  })
})
