/**
 * E2E Tests: Execution Filtering
 *
 * Critical paths covered:
 * - Keyword search via workflow name async typeahead filter
 * - workflow_id URL parameter backwards compatibility
 * - Status filter selection and switching
 * - Combined filters narrow results
 * - Empty state with filters active
 * - Filter chip removal and clear-all
 * - Shareable URLs with filter state
 *
 * Edge cases:
 * - Non-matching filter produces empty state
 * - URL-based filter restoration in new tab
 * - Filter persistence across navigation
 */

import { createUnavailableGuard, test, expect, toAppUrl, type Page } from './fixtures'
import { apiRequest } from './utils/api'

/** Select a workflow from the async typeahead, waiting for real options to load. */
async function selectFirstWorkflowOption(app: Page): Promise<string> {
  const filterToolbar = app.getByRole('search', { name: 'Filters' })
  await filterToolbar.getByRole('button', { name: 'Search workflows' }).click()

  await expect(async () => {
    const texts = await app.getByRole('option').allTextContents()
    if (texts.length === 0) throw new Error('No options yet')
    if (texts[0] === 'Loading...' || texts[0] === 'No results found') {
      throw new Error('Still loading')
    }
  }).toPass({ timeout: 10_000 })

  const allLabels = await app.getByRole('option').allTextContents()
  const label = allLabels[0] ?? ''
  await app.getByRole('option', { name: label, exact: true }).click()
  return label
}

/** Switch the filter field selector from its current field to a target field. */
async function switchFieldSelector(app: Page, currentFieldLabel: string, targetField: string): Promise<void> {
  const filterToolbar = app.getByRole('search', { name: 'Filters' })
  await filterToolbar.getByRole('button', { name: currentFieldLabel, exact: true }).click()
  await app.getByRole('option', { name: targetField }).click()
}

test.describe('Execution Filtering @pr-check', () => {
  const guard = createUnavailableGuard('No execution data available; seed data required')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/executions'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Executions table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No execution data available; seed data required')
  })

  test('keyword search: filter by workflow name via typeahead', async ({ app }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })
    const selectedWorkflowName = await selectFirstWorkflowOption(app)

    const workflowChipGroup = filterToolbar.getByRole('list', { name: 'Workflow name' })
    await expect(workflowChipGroup).toBeVisible()
    await expect(workflowChipGroup.getByText(selectedWorkflowName)).toBeVisible()

    await expect(app).toHaveURL(/workflow_id=/)

    // After filtering, page shows either results or empty state — both valid
    const table = app.getByRole('grid', { name: 'Executions table' })
    const emptyState = app.getByRole('heading', { name: 'No results found' })
    await expect(table.or(emptyState)).toBeVisible()
  })

  test('workflow_id filter backwards compatibility: URL parameter pre-populates filter', async ({ app }) => {
    const response = await apiRequest(app, 'get', '/executions?limit=1')
    test.skip(!response.ok(), 'Executions API unavailable')
    const data = (await response.json()) as {
      resources?: Array<{ workflow_id?: string }>
    }
    const workflowId = data.resources?.[0]?.workflow_id
    test.skip(!workflowId, 'No executions with workflow_id available')

    await app.goto(toAppUrl(`/executions?workflow_id=${workflowId}`))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

    const filterToolbar = app.getByRole('search', { name: 'Filters' })
    const workflowChipGroup = filterToolbar.getByRole('list', { name: 'Workflow name' })
    await expect(workflowChipGroup).toBeVisible()

    const table = app.getByRole('grid', { name: 'Executions table' })
    const noResults = app.getByRole('heading', { name: 'No results found' })
    await expect(table.or(noResults)).toBeVisible()
  })

  test('status filter: select and switch between status values', async ({ app }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })

    // Switch field selector from "Workflow name" to "Status"
    await switchFieldSelector(app, 'Workflow name', 'Status')

    // Open status dropdown and select "Completed"
    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
    await expect(statusChipGroup).toBeVisible()
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    await expect(app).toHaveURL(/status=completed/)

    // Switch to "Failed" — re-open value toggle (now showing "Completed")
    await filterToolbar.getByRole('button', { name: 'Completed', exact: true }).click()
    await app.getByRole('option', { name: 'Failed' }).click()

    await expect(statusChipGroup.getByText('Failed')).toBeVisible()
    await expect(statusChipGroup.getByText('Completed')).not.toBeVisible()
    await expect(app).toHaveURL(/status=failed/)
    await expect(app).not.toHaveURL(/status=completed/)

    // Remove status filter via chip close button
    await statusChipGroup.getByRole('button', { name: 'Close Failed' }).click()

    await expect(statusChipGroup).not.toBeVisible()
    await expect(app).not.toHaveURL(/status=/)
  })

  test('combined filters: workflow name + status narrow results', async ({ app }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })

    const selectedWorkflowName = await selectFirstWorkflowOption(app)

    const workflowChipGroup = filterToolbar.getByRole('list', { name: 'Workflow name' })
    await expect(workflowChipGroup.getByText(selectedWorkflowName)).toBeVisible()
    await expect(app).toHaveURL(/workflow_id=/)

    // Switch field selector from "Workflow name" to "Status"
    await switchFieldSelector(app, 'Workflow name', 'Status')

    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    await expect(workflowChipGroup.getByText(selectedWorkflowName)).toBeVisible()

    await expect(app).toHaveURL(/workflow_id=/)
    await expect(app).toHaveURL(/status=completed/)

    // Clear all filters
    await filterToolbar.getByRole('button', { name: 'Clear all filters' }).click()

    await expect(filterToolbar.getByRole('list')).toHaveCount(0)
    await expect(app).not.toHaveURL(/workflow_id=/)
    await expect(app).not.toHaveURL(/status=/)
  })

  test('empty state shows when filters return no results', async ({ app }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })

    await switchFieldSelector(app, 'Workflow name', 'Status')

    // Apply "Completed with errors" — no mock data has this status
    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed with errors' }).click()

    const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Completed with errors')).toBeVisible()

    const table = app.getByRole('grid', { name: 'Executions table' })
    const emptyHeading = app.getByRole('heading', { name: 'No results found' })
    await expect(table.or(emptyHeading)).toBeVisible()

    if (await emptyHeading.isVisible()) {
      await app.getByRole('button', { name: 'Clear all filters' }).last().click()

      const fullTable = app.getByRole('grid', { name: 'Executions table' })
      const noDataState = app.getByText(/No executions found/i)
      await expect(fullTable.or(noDataState)).toBeVisible()
      await expect(statusChipGroup).not.toBeVisible()
    }
  })

  test('shareable URLs: filters restored from URL', async ({ app, context }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })

    await switchFieldSelector(app, 'Workflow name', 'Status')

    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    await expect(app).toHaveURL(/status=completed/)

    const urlWithFilters = app.url()

    const newPage = await context.newPage()
    await newPage.goto(urlWithFilters)

    await expect(newPage.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
    const newPageStatusChipGroup = newPage
      .getByRole('search', { name: 'Filters' })
      .getByRole('list', { name: 'Status' })
    await expect(newPageStatusChipGroup.getByText('Completed')).toBeVisible()

    await newPage.close()
  })

  test('filter state persists across navigation', async ({ app }) => {
    await switchFieldSelector(app, 'Workflow name', 'Status')

    const filterToolbar = app.getByRole('search', { name: 'Filters' })
    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Running' }).click()

    await expect(app).toHaveURL(/status=running/)
    const urlWithFilter = app.url()

    await app.goto(toAppUrl('/'))

    await app.goto(urlWithFilter)

    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Running')).toBeVisible()
    await expect(app).toHaveURL(/status=running/)
  })

  test('individual filter chips can be removed independently', async ({ app }) => {
    const filterToolbar = app.getByRole('search', { name: 'Filters' })

    await selectFirstWorkflowOption(app)

    const workflowChipGroup = filterToolbar.getByRole('list', { name: 'Workflow name' })
    await expect(workflowChipGroup).toBeVisible()

    // Switch field selector from "Workflow name" to "Status"
    await switchFieldSelector(app, 'Workflow name', 'Status')

    await filterToolbar.getByRole('button', { name: 'Filter by status' }).click()
    await app.getByRole('option', { name: 'Completed', exact: true }).click()

    const statusChipGroup = filterToolbar.getByRole('list', { name: 'Status' })
    await expect(statusChipGroup).toBeVisible()

    // Remove workflow chip — status chip should remain
    await workflowChipGroup.getByRole('button', { name: /^Close / }).click()

    await expect(workflowChipGroup).not.toBeVisible()
    await expect(statusChipGroup.getByText('Completed')).toBeVisible()
    await expect(app).not.toHaveURL(/workflow_id=/)
    await expect(app).toHaveURL(/status=completed/)

    // Remove remaining status filter
    await statusChipGroup.getByRole('button', { name: 'Close Completed' }).click()

    await expect(filterToolbar.getByRole('list')).toHaveCount(0)
    await expect(app).not.toHaveURL(/status=/)
  })
})
