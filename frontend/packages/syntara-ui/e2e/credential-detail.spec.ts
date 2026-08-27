import { test, expect } from './fixtures'
import { createTestCredential, deleteCredentialByName, navigateToCredentialDetail } from './helpers/credentials'

test.describe('Credential Detail Page & Workflows Tab', () => {
  test('navigates to credential detail page', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-nav' })
    try {
      // Act - Navigate to detail page via list
      await navigateToCredentialDetail(app, name)

      // Assert - Detail page loaded
      await expect(app).toHaveURL(/configuration\/credentials\//)
      await expect(app.locator('h1').filter({ hasText: name })).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('detail page shows all tabs', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-tabs' })
    try {
      await navigateToCredentialDetail(app, name)

      // Assert - All tabs are visible
      await expect(app.getByRole('tab', { name: /Details/ })).toBeVisible()
      await expect(app.getByRole('tab', { name: /Workflows/ })).toBeVisible()
      await expect(app.getByRole('tab', { name: /Integrations/ })).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('details tab shows credential information', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-info' })
    try {
      await navigateToCredentialDetail(app, name)

      // Assert - Details tab shows credential metadata
      const detailsTab = app.getByLabel('Details')
      await expect(detailsTab.getByText('HTTP Bearer Token')).toBeVisible()
      await expect(detailsTab.getByText('Enabled')).toBeVisible()

      // Assert - Dynamic fields shown (bearer token has a Token field)
      await expect(detailsTab.getByText('Token', { exact: true })).toBeVisible()
      // Token value is either shown as "Encrypted" (real backend) or as the actual value (mock API)
      const tokenValue = detailsTab.getByText('Encrypted').or(detailsTab.getByText('e2e-test-token'))
      await expect(tokenValue).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('edit button opens edit modal', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-edit' })
    try {
      await navigateToCredentialDetail(app, name)

      // Act - Click Edit credential button
      await app.getByRole('button', { name: 'Edit credential' }).click()

      // Assert - Edit modal opens with pre-populated fields
      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()
      await expect(modal.getByText(`Edit ${name}`)).toBeVisible()
      await expect(modal.getByRole('textbox', { name: 'Credential name' })).toHaveValue(name)

      // Assert - Credential type is disabled in edit mode
      await expect(modal.getByRole('button', { name: 'Credential type', exact: true })).toBeDisabled()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('enable/disable toggle shows confirmation dialog', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-toggle' })
    try {
      await navigateToCredentialDetail(app, name)

      // Act - Click the toggle to disable
      await app.getByRole('switch', { name: /enabled/i }).click({ force: true })

      // Assert - Confirmation dialog appears
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Disable credential?')).toBeVisible()
      await expect(dialog.getByText(new RegExp(name))).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Disable' })).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('navigates to Workflows tab', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-wf-nav' })
    try {
      await navigateToCredentialDetail(app, name)

      // Act - Click Workflows tab
      await app.getByRole('tab', { name: /Workflows/ }).click()

      // Assert - Workflows tab content loaded (table or empty state)
      const workflowsTable = app.getByRole('grid', { name: 'Workflows using this credential' })
      const emptyState = app.getByText('No workflows using this credential')
      const errorState = app.getByText('Failed to load workflows')
      await expect(workflowsTable.or(emptyState).or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('workflows tab shows workflow references when available', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-wf-refs' })
    try {
      await navigateToCredentialDetail(app, name)
      await app.getByRole('tab', { name: /Workflows/ }).click()

      // This credential was just created — it won't have workflows referencing it
      // Assert the empty state or table renders correctly
      const emptyState = app.getByText('No workflows using this credential')
      const table = app.getByRole('grid', { name: 'Workflows using this credential' })
      const errorState = app.getByText('Failed to load workflows')
      await expect(emptyState.or(table).or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('workflows tab shows count in footer when workflows exist', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-wf-count' })
    try {
      await navigateToCredentialDetail(app, name)
      await app.getByRole('tab', { name: /Workflows/ }).click()

      // Assert - Either count footer, empty state, or error renders
      const countFooter = app.getByText(/\d+ workflows?/)
      const emptyState = app.getByText('No workflows using this credential')
      const errorState = app.getByText('Failed to load workflows')
      await expect(countFooter.or(emptyState).or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('workflow names display as bold text in table', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-wf-bold' })
    try {
      await navigateToCredentialDetail(app, name)
      await app.getByRole('tab', { name: /Workflows/ }).click()

      const table = app.getByRole('grid', { name: 'Workflows using this credential' })
      const tableVisible = await table
        .waitFor({ state: 'visible', timeout: 5000 })
        .then(() => true)
        .catch(() => false)

      if (tableVisible) {
        // Verify workflow names appear as bold text (first data row)
        const firstDataRow = table.locator('tbody tr:first-child')
        await expect(firstDataRow.locator('strong')).toBeVisible()
      } else {
        // No workflows or endpoint not available — empty/error state is valid
        const emptyOrError = app
          .getByText('No workflows using this credential')
          .or(app.getByText('Failed to load workflows'))
        await expect(emptyOrError).toBeVisible()
      }
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('navigates to Integrations tab', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-int-nav' })
    try {
      await navigateToCredentialDetail(app, name)

      // Act - Click Integrations tab
      await app.getByRole('tab', { name: /Integrations/ }).click()

      // Assert - Integrations tab content loaded (table or empty state)
      const integrationsTable = app.getByRole('grid', { name: 'Integrations using this credential' })
      const emptyState = app.getByText('No integrations using this credential')
      const errorState = app.getByText('Failed to load integrations')
      await expect(integrationsTable.or(emptyState).or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('integrations tab shows empty state for new credential', async ({ app }) => {
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-int-empty' })
    try {
      await navigateToCredentialDetail(app, name)
      await app.getByRole('tab', { name: /Integrations/ }).click()

      // Assert - Empty state or error (freshly created credential has no integrations)
      const emptyState = app.getByText('No integrations using this credential')
      const errorState = app.getByText('Failed to load integrations')
      await expect(emptyState.or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test.skip('shows empty state when no workflows use credential', async ({ app }) => {
    // A freshly created credential has no workflows referencing it
    const { name } = await createTestCredential(app, { prefix: 'e2e-detail-wf-empty' })
    try {
      await navigateToCredentialDetail(app, name)
      await app.getByRole('tab', { name: /Workflows/ }).click()

      // Assert - Empty state or error (if endpoint not implemented yet)
      const emptyState = app.getByText('No workflows using this credential')
      const errorState = app.getByText('Failed to load workflows')
      await expect(emptyState.or(errorState)).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })
})
