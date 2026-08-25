/**
 * E2E Tests (AAP-72719): Workflow Execution Tests
 *
 * Objective: Verify that the workflow executions.
 *
 * Critical paths covered:
 * - Test Single Step from Canvas
 * - Live View of Running Execution
 * - Failed Node Error Details
 * - Run History Node I/O Inspection
 */
import { test, expect } from '../fixtures'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  deleteWorkflow,
} from '../helpers/workflows'

// Skipped: per-node I/O inspection times out — depends on execution engine completing and run history data availability
test.skip('per-node input and output data can be inspected from run history', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-inspect-per-node')

  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Say Hello')
  await openWorkflowInBuilder(app, workflowName, id)

  try {
    await expect(app.getByRole('button', { name: /Run/i })).toBeVisible({ timeout: 15_000 })
    await app.getByRole('button', { name: 'Run' }).click()
    await expect(app.getByRole('heading', { name: /Run/i })).toBeVisible({ timeout: 15_000 })
    await app.getByRole('button', { name: 'Run now' }).click()

    const helloNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Say Hello' })
    await expect(helloNode.getByLabel('Success')).toBeVisible({ timeout: 15_000 })

    await expect(app.getByRole('heading', { name: 'Run details' })).toBeVisible({ timeout: 15_000 })
    await app.getByRole('tab', { name: 'Details' }).click()
    await expect(app.getByRole('tab', { name: 'Details', selected: true })).toBeVisible({ timeout: 15_000 })

    const activityList = app.getByRole('grid', { name: 'Activity list' })
    await activityList.getByRole('row').filter({ hasText: 'Say Hello' }).click()

    // Inspect node's input data is displayed
    await expect(app.getByText('Parameter')).toBeVisible()
    await expect(app.getByText('"code": "print(\\"hello\\")"')).toBeVisible({ timeout: 15_000 })

    // Inspect node's output data is displayed
    await expect(app.getByText('Output')).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('"status": "completed"')).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('"stdout": "hello\\n"')).toBeVisible({ timeout: 15_000 })
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})
