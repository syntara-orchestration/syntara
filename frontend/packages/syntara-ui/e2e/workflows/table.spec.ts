/**
 * E2E Tests (ANSTRAT-1845): Workflows Table — Display and Navigation
 *
 *  Critical paths covered:
 * - Workflows table displays existing workflows with all required columns
 * - Clicking a workflow name navigates to the workflow builder
 * - Empty state displays when no workflows exist (filtered view)
 *
 * Edge cases:
 * - Table displays status, last run timestamps, and action controls
 * - Workflows can be searched and filtered
 */

import { test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from '../seeds/resources'
import { ensureProject } from '../utils/api'

test.describe('Workflows Table - Display and Navigation', () => {
  test('workflows table displays with name and state columns', async ({ app }) => {
    // Create a workflow specifically for this test
    const project = await ensureProject(app)
    const workflowName = buildUniqueName('e2e-table-display')
    const workflow = await createWorkflowViaApi(app, {
      name: workflowName,
      projectId: project?.id,
    })

    if (!workflow) throw new Error('Failed to create test workflow')

    try {
      // Navigate to workflows page
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      // Verify table exists
      const table = app.getByRole('grid', { name: 'Workflows table' })
      await expect(table).toBeVisible()

      // Verify column headers exist
      await expect(table.getByRole('columnheader', { name: 'Name' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Created at' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Updated at' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'State' })).toBeVisible()

      // Verify our workflow row exists
      await expect(table.getByRole('row', { name: new RegExp(workflowName) })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('clicking a workflow name navigates to the workflow builder', async ({ app }) => {
    // Create a workflow for this test
    const project = await ensureProject(app)
    const workflowName = buildUniqueName('e2e-nav')
    const workflow = await createWorkflowViaApi(app, {
      name: workflowName,
      projectId: project?.id,
    })

    if (!workflow) throw new Error('Failed to create test workflow')

    try {
      // Navigate to workflows page and filter for our specific workflow
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const table = app.getByRole('grid', { name: 'Workflows table' })
      const workflowRow = table.getByRole('row', { name: new RegExp(workflowName) })
      await expect(workflowRow).toBeVisible()

      await workflowRow.getByRole('link', { name: workflowName, exact: true }).click()

      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('workflows table displays action controls (kebab menu)', async ({ app }) => {
    // Create a workflow specifically for this test
    const project = await ensureProject(app)
    const workflowName = buildUniqueName('e2e-kebab')
    const workflow = await createWorkflowViaApi(app, {
      name: workflowName,
      projectId: project?.id,
    })

    if (!workflow) throw new Error('Failed to create test workflow')

    try {
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      // Filter by workflow name
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Wait for filter chip to appear
      const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
      await expect(nameChipGroup).toBeVisible()

      // Wait for the workflow row
      const table = app.getByRole('grid', { name: 'Workflows table' })
      const workflowRow = table.getByRole('row', { name: new RegExp(workflowName) })
      await expect(workflowRow).toBeVisible({ timeout: 15000 })

      // Verify kebab menu
      const kebabToggle = workflowRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await expect(kebabToggle).toBeVisible()

      await kebabToggle.click({ force: true })

      await expect(app.getByRole('menuitem', { name: /Delete workflow/i })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('empty state displays when no workflows match filter', async ({ app }) => {
    // Create a workflow to ensure we have data, then filter for something else
    const project = await ensureProject(app)
    const workflowName = buildUniqueName('e2e-empty-state')
    const workflow = await createWorkflowViaApi(app, {
      name: workflowName,
      projectId: project?.id,
    })

    if (!workflow) throw new Error('Failed to create test workflow')

    try {
      // Navigate to workflows page
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      // Filter for a name that definitely won't match our created workflow
      const impossibleName = `zzz-nonexistent-${Date.now()}`
      await app.getByPlaceholder('Filter by name').fill(impossibleName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
      await expect(nameChipGroup).toBeVisible()

      // Empty state should be visible
      await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()

      // Verify "Clear all filters" button exists in empty state
      await expect(app.getByRole('button', { name: 'Clear all filters' }).last()).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('multiple workflows display in table with unique identifiers', async ({ app }) => {
    // Create 2 workflows for this test
    const project = await ensureProject(app)
    const projectId = project?.id
    const prefix = buildUniqueName('e2e-multi')

    const workflow1 = await createWorkflowViaApi(app, {
      name: `${prefix}-workflow-1`,
      projectId,
    })

    const workflow2 = await createWorkflowViaApi(app, {
      name: `${prefix}-workflow-2`,
      projectId,
    })

    if (!workflow1 || !workflow2) throw new Error('Failed to create test workflows')

    try {
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      // Filter by prefix to show only our test workflows
      await app.getByPlaceholder('Filter by name').fill(prefix)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Check if table exists
      const table = app.getByRole('grid', { name: 'Workflows table' })
      await expect(table).toBeVisible({ timeout: 5000 })

      // Verify both workflows are visible
      await expect(table.getByRole('row', { name: new RegExp(workflow1.name) })).toBeVisible()
      await expect(table.getByRole('row', { name: new RegExp(workflow2.name) })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow1.id)
      await deleteWorkflowViaApi(app, workflow2.id)
    }
  })
})
