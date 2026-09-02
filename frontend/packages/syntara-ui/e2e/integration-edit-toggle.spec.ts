/**
 * E2E Tests: Integration Edit, Delete & Enable/Disable (Tests 22, 24, 25)
 *
 * Covers:
 * - Test 22: Edit integration — update name and verify persistence
 * - Test 24: Delete integration — full confirmation flow with checkbox
 * - Test 25: Enable/disable toggle — disable shows indicator, re-enable restores
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { createIntegrationViaApi, deleteIntegrationViaApi } from './seeds/resources'
import { getAuthToken } from './utils/api'

test.describe('Integration Edit, Delete & Enable/Disable', () => {
  test('edit integration updates name and shows success alert', async ({ app }) => {
    const originalName = buildUniqueName('e2e-edit-t22')
    const updatedName = buildUniqueName('e2e-edit-t22-updated')
    let integrationId: string | undefined

    try {
      const token = await getAuthToken(app)
      const seeded = await createIntegrationViaApi(app, { name: originalName, token: token ?? undefined })
      if (!seeded) throw new Error('Failed to create integration')
      integrationId = seeded.id

      await app.goto(toAppUrl('/configuration/integrations'))
      await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

      // Filter to find the integration
      await app.getByPlaceholder('Filter by name').fill(originalName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(originalName) })
      await expect(row).toBeVisible({ timeout: 30_000 })

      // Navigate to the detail page
      await row.getByRole('link', { name: originalName }).click()
      await expect(app.getByRole('heading', { name: originalName })).toBeVisible({ timeout: 15_000 })

      // Open the edit form via the Edit button
      await app.getByRole('button', { name: /Edit/i }).click()

      // Verify the name field is pre-populated
      const nameInput = app.getByRole('textbox', { name: /name/i })
      await expect(nameInput).toHaveValue(originalName)

      // Update the name
      await nameInput.clear()
      await nameInput.fill(updatedName)

      // Save the edit
      await app.getByRole('button', { name: /Save/i }).click()

      // Verify success alert
      await expect(app.getByText('Integration updated')).toBeVisible({ timeout: 10_000 })

      // Verify the updated name is shown on the detail page
      await expect(app.getByRole('heading', { name: updatedName })).toBeVisible({ timeout: 10_000 })
    } finally {
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
    }
  })

  test('delete integration removes it from list after confirmation', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-delete-t24')
    let integrationId: string | undefined

    try {
      const token = await getAuthToken(app)
      const seeded = await createIntegrationViaApi(app, { name: integrationName, token: token ?? undefined })
      if (!seeded) throw new Error('Failed to create integration')
      integrationId = seeded.id

      await app.goto(toAppUrl('/configuration/integrations'))
      await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

      // Filter to find the integration
      await app.getByPlaceholder('Filter by name').fill(integrationName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(integrationName) })
      await expect(row).toBeVisible({ timeout: 30_000 })

      // Open kebab menu and click Delete
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: /Delete integration/i }).click()

      // Verify confirmation dialog
      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()
      await expect(modal.getByText('Delete integration?')).toBeVisible()
      await expect(modal.getByText(new RegExp(integrationName))).toBeVisible()

      // Delete button should be disabled before checkbox
      const deleteButton = modal.getByRole('button', { name: 'Delete' })
      await expect(deleteButton).toBeDisabled()

      // Check the acknowledgement checkbox
      await modal.getByRole('checkbox').click()
      await expect(deleteButton).toBeEnabled()

      // Confirm deletion
      await deleteButton.click()
      await expect(modal).not.toBeVisible()

      // Verify success alert
      await expect(app.getByText('Integration deleted')).toBeVisible({ timeout: 10_000 })

      // Verify integration is removed from the list
      await expect(row).not.toBeVisible({ timeout: 10_000 })

      // Clear the reference so cleanup doesn't try to delete again
      integrationId = undefined
    } finally {
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
    }
  })

  test('disable integration shows disabled state and re-enable restores it', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-toggle-t25')
    let integrationId: string | undefined

    try {
      const token = await getAuthToken(app)
      const seeded = await createIntegrationViaApi(app, { name: integrationName, token: token ?? undefined })
      if (!seeded) throw new Error('Failed to create integration')
      integrationId = seeded.id

      await app.goto(toAppUrl('/configuration/integrations'))
      await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

      // Filter to find the integration
      await app.getByPlaceholder('Filter by name').fill(integrationName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(integrationName) })
      await expect(row).toBeVisible({ timeout: 30_000 })

      // Toggle to disable — should open a confirmation dialog
      const toggle = row.getByRole('switch')
      await expect(toggle).toBeChecked()
      await toggle.click({ force: true })

      // Confirm disable in the dialog
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText(/Disable integration/i)).toBeVisible()
      await dialog.getByRole('button', { name: 'Disable' }).click()
      await expect(dialog).not.toBeVisible()

      // Verify the toggle shows disabled state
      await expect(toggle).not.toBeChecked()

      // Re-enable the integration (direct toggle, no confirmation needed)
      await toggle.click({ force: true })
      await expect(toggle).toBeChecked()
    } finally {
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
    }
  })
})
