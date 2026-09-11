import { type Locator } from '@playwright/test'

import { type Page, test, expect, toAppUrl } from './fixtures'
import {
  createTestCredential,
  deleteCredentialByName,
  disableCredentialFromRow,
  filterCredentialByName,
  goToCredentialsList,
  navigateToCredentialDetail,
  openDisableDialogFromRow,
  waitForDisableDialogReady,
} from './helpers/credentials'

function listRowToggle(row: Locator) {
  return row.getByRole('switch')
}

function detailPageToggle(app: Page) {
  return app.getByRole('switch', { name: /enabled/i })
}

test.describe('Credential Enable/Disable State Management', () => {
  test.describe.configure({ mode: 'serial' })

  test('toggle on enabled credential opens disable confirmation', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-toggle-open' })
    try {
      await goToCredentialsList(app)
      await filterCredentialByName(app, name)
      const row = app.getByRole('row', { name: new RegExp(name) })
      const dialog = await openDisableDialogFromRow(app, row, name)
      await expect(dialog).toBeVisible()
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
      const dialog = await openDisableDialogFromRow(app, row, name)
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
      const dialog = await openDisableDialogFromRow(app, row)
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
      const dialog = await openDisableDialogFromRow(app, row)
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
      // Gate on the PATCH: the switch flips optimistically, so `not.toBeChecked()`
      // alone is satisfied before the request goes out and the goto below would
      // abort it — leaving the credential enabled on the server.
      await disableCredentialFromRow(app, row)

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
