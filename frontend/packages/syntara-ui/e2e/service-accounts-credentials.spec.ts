/**
 * E2E Tests: Service Accounts — Credentials Tab
 *
 * Test cases covered:
 * - UI-9: Secret rotation flow with grace period display
 */
import { test, expect } from './fixtures'
import { createTestServiceAccount, deleteServiceAccountViaApi, goToServiceAccountTab } from './helpers/service-accounts'

test.describe('UI-9: Secret Rotation Grace Period Display', () => {
  let sa: { id: string; name: string }

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sa = await createTestServiceAccount(page, { prefix: 'sa-rotate' })
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

  test('rotation with grace period shows indicator in credentials table', async ({ app }) => {
    await goToServiceAccountTab(app, sa, 'Credentials')

    // Create a credential — this opens the CreateCredentialModal first
    await app.getByRole('button', { name: 'Create credential' }).click()

    const createModal = app.getByRole('dialog')
    await expect(createModal.getByRole('heading', { name: 'Create credential' })).toBeVisible()
    await createModal.getByRole('button', { name: 'Create credential' }).click()

    // Handle the secret reveal modal for the new credential
    await expect(createModal.getByText('New credential created')).toBeVisible({ timeout: 15_000 })
    await createModal.getByLabel('I have saved the new secret').check()
    await createModal.getByRole('button', { name: 'Close' }).click()

    // Wait for the credential row to appear in the table — the freshly created
    // SA has exactly one credential after creation, so a single row with nx_sa_ matches
    const credRow = app.getByRole('row').filter({ hasText: /nx_sa_/ })
    await expect(credRow).toBeVisible()

    // Open kebab menu on the credential → "Rotate secret"
    await credRow.getByRole('button', { name: /Actions for/ }).click()
    await app.getByRole('menuitem', { name: /Rotate secret/ }).click()

    // Verify rotation dialog
    const rotateDialog = app.getByRole('dialog')
    await expect(rotateDialog.getByText('Rotate client secret?')).toBeVisible()

    // Default grace period is "1 hour" — leave as-is and confirm
    await rotateDialog.getByRole('button', { name: 'Rotate secret' }).click()

    // Verify the secret reveal modal with grace period alert
    const secretModal = app.getByRole('dialog')
    await expect(secretModal.getByText('New client secret')).toBeVisible()
    await expect(secretModal.getByText('Grace period active')).toBeVisible()

    // Close the reveal modal
    await secretModal.getByLabel('I have saved the new secret').check()
    await secretModal.getByRole('button', { name: 'Close' }).click()

    // Verify the grace period indicator appears in the credentials table
    await expect(app.getByText(/Rotating — .+ left/)).toBeVisible()
  })
})
