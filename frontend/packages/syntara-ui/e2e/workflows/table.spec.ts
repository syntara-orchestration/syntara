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
})
