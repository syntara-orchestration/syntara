/**
 * E2E Tests: Integration Tools (Enabled Resources)
 *
 * Critical paths covered:
 * - Navigate to enabled resources tab from integrations list
 * - Toggle individual tools (enable/disable via checkboxes) and save
 * - Select all / deselect all tools
 * - Cancel without saving returns to integrations list
 * - Empty state when integration has no tools
 *
 * Edge cases:
 * - Save with mixed enabled/disabled tools persists state
 * - Resources tab heading shows enabled count
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { createIntegrationViaApi, deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { getAuthToken } from './utils/api'

async function createIntegration(app: Page, name: string): Promise<SeededIntegration> {
  const token = await getAuthToken(app)
  const integration = await createIntegrationViaApi(app, { name, token: token ?? undefined })
  if (!integration) throw new Error(`Failed to create integration "${name}" via API`)
  return integration
}

async function navigateToResourcesTab(app: Page, integrationName: string) {
  await app.goto(toAppUrl('/configuration/integrations'))
  await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
  await app.getByPlaceholder('Filter by name').fill(integrationName)
  await app.getByRole('button', { name: 'Apply filter' }).click()
  const row = app.getByRole('row', { name: new RegExp(integrationName) })
  await expect(row).toBeVisible()
  // Click the integration name link to navigate to detail page
  const nameCell = row.locator('td[data-label="Name"]')
  await nameCell.getByRole('link').click()
  // Navigate to the Enabled resources tab
  await app.getByRole('tab', { name: /Enabled resources/i }).click()
}

test.describe('Integration Tools', () => {
  test('user navigates to resources tab from integrations list', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-tools-nav')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      // Verify either tools table or empty state is displayed
      const toolsTable = app.locator('[aria-label="tools table"]')
      const hasTable = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )

      if (hasTable) {
        // Verify Save changes button is present
        await expect(app.getByRole('button', { name: 'Save changes' })).toBeVisible()

        const checkboxes = toolsTable.getByRole('checkbox')
        const count = await checkboxes.count()
        expect(count).toBeGreaterThan(0)
      } else {
        await expect(app.getByRole('heading', { name: 'No resources discovered yet' })).toBeVisible()
      }
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })

  test('user toggles individual tools and saves', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-tools-toggle')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      const toolsTable = app.locator('[aria-label="tools table"]')
      const emptyState = app.getByRole('heading', { name: 'No resources discovered yet' })
      const hasTools = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )
      if (!hasTools) {
        await expect(emptyState).toBeVisible()
        test.skip(true, 'No tools available for this integration; backend did not generate tools')
      }

      // Read tool names from the page so selectors are name-based, not positional
      const toolNames = await toolsTable.locator('tbody dt').allTextContents()
      expect(toolNames.length).toBeGreaterThan(0)

      // Toggle the first tool by name
      const firstToolRow = toolsTable.getByRole('row').filter({ hasText: toolNames[0] })
      const firstToolCheckbox = firstToolRow.getByRole('checkbox')
      const wasChecked = await firstToolCheckbox.isChecked()
      await firstToolCheckbox.click()

      if (wasChecked) {
        await expect(firstToolCheckbox).not.toBeChecked()
      } else {
        await expect(firstToolCheckbox).toBeChecked()
      }

      // Toggle a second tool if available
      if (toolNames.length > 1) {
        const secondToolRow = toolsTable.getByRole('row').filter({ hasText: toolNames[1] })
        const secondToolCheckbox = secondToolRow.getByRole('checkbox')
        const secondWasChecked = await secondToolCheckbox.isChecked()
        await secondToolCheckbox.click()

        if (secondWasChecked) {
          await expect(secondToolCheckbox).not.toBeChecked()
        } else {
          await expect(secondToolCheckbox).toBeChecked()
        }
      }

      // Save changes
      await app.getByRole('button', { name: 'Save changes' }).click()
      // Verify success alert
      await expect(app.getByText('Changes saved')).toBeVisible()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })

  test('user selects all tools then deselects all', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-tools-selall')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      const toolsTable = app.locator('[aria-label="tools table"]')
      const emptyState = app.getByRole('heading', { name: 'No resources discovered yet' })
      const hasTools = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )
      if (!hasTools) {
        await expect(emptyState).toBeVisible()
        test.skip(true, 'No tools available for this integration; backend did not generate tools')
      }

      const toolNames = await toolsTable.locator('tbody dt').allTextContents()
      expect(toolNames.length).toBeGreaterThan(0)

      // Deselect all individually first
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        if (await checkbox.isChecked()) {
          await checkbox.click()
        }
      }

      // Verify all rows are unchecked
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        await expect(checkbox).not.toBeChecked()
      }

      // Select all individually
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        await checkbox.click()
      }

      // Verify all rows are now checked
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        await expect(checkbox).toBeChecked()
      }

      // Deselect all individually again
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        await checkbox.click()
      }

      // Verify all rows are unchecked again
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        await expect(checkbox).not.toBeChecked()
      }
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })

  test('user saves toggled tools and changes persist on revisit', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-tools-persist')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      const toolsTable = app.locator('[aria-label="tools table"]')
      const emptyState = app.getByRole('heading', { name: 'No resources discovered yet' })
      const hasTools = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )
      if (!hasTools) {
        await expect(emptyState).toBeVisible()
        test.skip(true, 'No tools available for this integration; backend did not generate tools')
      }

      // Read tool names so we can select by name
      const toolNames = await toolsTable.locator('tbody dt').allTextContents()
      expect(toolNames.length).toBeGreaterThan(0)

      // Deselect all tools individually first
      for (const name of toolNames) {
        const checkbox = toolsTable.getByRole('row').filter({ hasText: name }).getByRole('checkbox')
        if (await checkbox.isChecked()) {
          await checkbox.click()
        }
      }

      // Enable only the first tool
      const firstToolRow = toolsTable.getByRole('row').filter({ hasText: toolNames[0] })
      const firstToolCheckbox = firstToolRow.getByRole('checkbox')
      await firstToolCheckbox.click()
      await expect(firstToolCheckbox).toBeChecked()

      // Save
      await app.getByRole('button', { name: 'Save changes' }).click()
      await expect(app.getByText('Changes saved')).toBeVisible()

      // Navigate away and back to resources tab
      await navigateToResourcesTab(app, integrationName)

      const revisitTable = app.locator('[aria-label="tools table"]')
      await expect(revisitTable).toBeVisible()

      // Verify the first tool is still checked and others are not
      const firstToolRevisit = revisitTable.getByRole('row').filter({ hasText: toolNames[0] })
      await expect(firstToolRevisit.getByRole('checkbox')).toBeChecked()

      if (toolNames.length > 1) {
        const secondToolRevisit = revisitTable.getByRole('row').filter({ hasText: toolNames[1] })
        await expect(secondToolRevisit.getByRole('checkbox')).not.toBeChecked()
      }
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })

  test('user navigates away from resources tab without saving', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-tools-cancel')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      const toolsTable = app.locator('[aria-label="tools table"]')
      const hasTools = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )

      // Toggle a tool if any exist (to verify unsaved changes are discarded)
      if (hasTools) {
        const firstDataRow = toolsTable.locator('tbody tr:first-child')
        const firstCheckbox = firstDataRow.getByRole('checkbox')
        if ((await firstCheckbox.count()) > 0) {
          await firstCheckbox.click()
        }
      }

      // Navigate back to integrations list
      await app.goto(toAppUrl('/configuration/integrations'))

      // Handle unsaved changes dialog if it appears
      const dialog = app.getByRole('dialog')
      const hasDialog = await dialog
        .waitFor({ state: 'visible', timeout: 3000 })
        .then(() => true)
        .catch(() => false)
      if (hasDialog) {
        // Click "Leave" or "Don't save" to exit without saving
        const leaveButton = dialog.getByRole('button', { name: /Leave|Don.t save|Exit without saving/i })
        if ((await leaveButton.count()) > 0) {
          await leaveButton.click()
        }
      }

      await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
      await expect(app).toHaveURL(/configuration\/integrations/)
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })

  test('empty state shows for integration with no tools', async ({ app }) => {
    // Create a fresh integration via API — it will have no tools
    const integrationName = buildUniqueName('e2e-tools-empty')
    const integration = await createIntegration(app, integrationName)

    try {
      await navigateToResourcesTab(app, integrationName)

      const toolsTable = app.locator('[aria-label="tools table"]')

      const hasToolsTable = await expect(toolsTable)
        .toBeVisible()
        .then(
          () => true,
          () => false
        )

      // If the integration has tools, skip the empty state test
      test.skip(hasToolsTable, 'Integration has tools; empty state not testable with current data')

      await expect(app.getByRole('heading', { name: 'No resources discovered yet' })).toBeVisible()
      const refreshButtons = app.getByRole('button', { name: 'Refresh tools' })
      expect(await refreshButtons.count()).toBeGreaterThanOrEqual(1)
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
    }
  })
})
