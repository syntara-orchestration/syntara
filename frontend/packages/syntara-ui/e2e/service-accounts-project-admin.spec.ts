/**
 * E2E Tests: Service Accounts — Full CRUD Lifecycle
 *
 * Test cases covered:
 * - UI-11: Admin can create, edit, and delete a project-scoped service account
 */
import { test, expect } from './fixtures'
import {
  createServiceAccountViaUI,
  createTestServiceAccount,
  deleteServiceAccountByName,
  deleteServiceAccountViaApi,
  goToServiceAccountDetail,
} from './helpers/service-accounts'
import { buildUniqueName } from './helpers/workflows'

test.describe('UI-11: Service Account CRUD Lifecycle', () => {
  test('admin can create a service account via UI', async ({ app }) => {
    const saName = buildUniqueName('sa-create')

    const creds = await createServiceAccountViaUI(app, { name: saName })

    try {
      expect(creds.clientId).toBeTruthy()
      expect(creds.clientSecret).toBeTruthy()
    } finally {
      await deleteServiceAccountByName(app, saName)
    }
  })

  test.describe('edit and delete', () => {
    let sa: { id: string; name: string }

    test.beforeAll(async ({ browser }) => {
      const page = await browser.newPage()
      try {
        sa = await createTestServiceAccount(page, { prefix: 'sa-crud' })
      } finally {
        await page.close()
      }
    })

    test.afterAll(async ({ browser }) => {
      if (!sa) return
      const page = await browser.newPage()
      try {
        await deleteServiceAccountViaApi(page, sa.id)
      } finally {
        await page.close()
      }
    })

    test('admin can edit and delete a service account', async ({ app }) => {
      await goToServiceAccountDetail(app, sa)

      // Edit the service account name
      const editedName = `${sa.name}-edited`
      await app.getByRole('button', { name: 'Edit service account' }).click()
      const editModal = app.getByRole('dialog')
      await editModal.getByRole('textbox', { name: 'Name', exact: true }).clear()
      await editModal.getByRole('textbox', { name: 'Name', exact: true }).fill(editedName)
      await editModal.getByRole('button', { name: 'Save service account' }).click()

      await expect(app.getByText('Service account updated')).toBeVisible()
      await expect(app.getByRole('heading', { level: 1, name: editedName })).toBeVisible()

      // Delete the service account via kebab menu
      await app.getByRole('button', { name: 'Service account actions' }).click()
      await app.getByRole('menuitem', { name: 'Delete service account' }).click()

      const deleteDialog = app.getByRole('dialog')
      await deleteDialog.getByRole('checkbox', { name: /I understand/i }).check()
      await deleteDialog.getByRole('button', { name: 'Delete service account' }).click()

      // Verify redirect to list
      await expect(app.getByRole('tab', { name: 'Service accounts', exact: true })).toBeVisible()
    })
  })
})
