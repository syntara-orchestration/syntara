import { type Page, test, expect, toAppUrl } from './fixtures'
import {
  createTestCredential,
  deleteCredentialByName,
  goToCredentialsList,
  navigateToCredentialDetail,
} from './helpers/credentials'

async function filterCredentialByName(app: Page, name: string) {
  await app.getByPlaceholder('Filter by keyword').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

function listRowToggle(row: import('@playwright/test').Locator) {
  return row.getByRole('switch')
}

function detailPageToggle(app: Page) {
  return app.getByRole('switch', { name: /enabled/i })
}

/** Wait until usage checks finish so the Disable action is actually clickable. */
async function waitForDisableDialogReady(dialog: import('@playwright/test').Locator, credentialName?: string) {
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

test.describe('Credential Enable/Disable State Management', () => {
  test.describe.configure({ mode: 'serial' })

  test('toggle on enabled credential opens disable confirmation', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-open' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      await row.waitFor({ state: 'visible', timeout: 10_000 })
      await listRowToggle(row).click({ force: true })

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await waitForDisableDialogReady(dialog, name)
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('disable confirmation dialog shows warning with credential name', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-warn' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      await listRowToggle(row).click({ force: true })

      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog, name)
      await expect(dialog.getByText(/You can re-enable the credential at any time/)).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('confirm disable changes credential state', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-confirm' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      await listRowToggle(row).click({ force: true })

      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog)
      await dialog.getByRole('button', { name: 'Disable' }).click()

      await expect(dialog).not.toBeVisible()
      await expect(listRowToggle(row)).not.toBeChecked()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('cancel disable keeps credential enabled', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-cancel' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      await listRowToggle(row).click({ force: true })

      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog)
      await dialog.getByRole('button', { name: 'Cancel' }).click()

      await expect(dialog).not.toBeVisible()
      await expect(listRowToggle(row)).toBeChecked()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('re-enable credential without confirmation', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-reenable', enabled: false })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })

      await expect(listRowToggle(row)).not.toBeChecked()

      await listRowToggle(row).click({ force: true })

      await expect(listRowToggle(row)).toBeChecked()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('disable from detail page', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-detail' })
    try {
      await navigateToCredentialDetail(app, name)

      await detailPageToggle(app).click({ force: true })

      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog)
      await dialog.getByRole('button', { name: 'Disable' }).click()

      await expect(detailPageToggle(app)).not.toBeChecked()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('state badge reflects current state on detail page', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-badge' })
    try {
      await navigateToCredentialDetail(app, name)

      const detailsTab = app.getByLabel('Details')
      await expect(detailsTab.getByText('Enabled')).toBeVisible()

      await detailPageToggle(app).click({ force: true })
      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog)
      await dialog.getByRole('button', { name: 'Disable' }).click()

      await expect(detailPageToggle(app)).not.toBeChecked()
      await expect(detailsTab.getByText('Disabled')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('state persists across page navigation', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-persist' })
    try {
      // Disable the credential
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      await listRowToggle(row).click({ force: true })
      const dialog = app.getByRole('dialog')
      await waitForDisableDialogReady(dialog)
      await dialog.getByRole('button', { name: 'Disable' }).click()
      await expect(listRowToggle(row)).not.toBeChecked()

      // Navigate away and back
      await app.goto(toAppUrl('/workflows'))
      await expect(app.locator('h1').filter({ hasText: 'Workflows' })).toBeVisible()
      await goToCredentialsList(app)

      // Filter to find our credential
      await filterCredentialByName(app, name)

      const updatedRow = app.getByRole('row', { name: new RegExp(name) })
      await updatedRow.waitFor({ state: 'visible', timeout: 10_000 })
      await expect(listRowToggle(updatedRow)).not.toBeChecked()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })
})
