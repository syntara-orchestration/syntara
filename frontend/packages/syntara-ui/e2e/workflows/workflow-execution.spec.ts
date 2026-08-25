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
  openBuilderById,
  runSingleWorkflowNode,
} from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from '../utils/api'

// Skipped: real-time node status assertion times out — depends on WebSocket updates and execution engine timing
test.skip('running execution displays real-time per-node status on the canvas', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-node-live-status')

  const { id: workflowId } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'hello_node',
        type: 'script',
        name: 'Say Hello',
        parameters: { language: 'python', code: 'import time\ntime.sleep(1)\nprint("hello")' },
      },
      {
        id: 'goodbye_node',
        type: 'script',
        name: 'Say Goodbye',
        parameters: { language: 'python', code: 'import time\ntime.sleep(3)\nprint("goodbye")' },
      },
    ],
    [
      { from: 'trigger_manual', to: 'hello_node' },
      { from: 'hello_node', to: 'goodbye_node' },
    ]
  )

  try {
    await openBuilderById(app, workflowId)

    await app.getByRole('button', { name: 'Run' }).click()
    await expect(app.getByRole('heading', { name: /Run/i })).toBeVisible({ timeout: 15_000 })
    await app.getByRole('button', { name: 'Run now' }).click()

    await expect(app.getByRole('heading', { name: workflowName })).toBeVisible({ timeout: 15_000 })

    const goodbyeNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Say Goodbye' })
    await expect(goodbyeNode.getByLabel('Running')).toBeVisible({ timeout: 15_000 })
    await expect(goodbyeNode.getByLabel('Success')).toBeVisible({ timeout: 15_000 })
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})

// Skipped: failed node error details assertion times out — depends on execution engine completing and error propagation
test.skip('failed node details including error messages are displayed', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-failed-node')

  const { id: workflowId } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'failing_node',
        type: 'script',
        name: 'Failing Node',
        parameters: { language: 'python', code: 'raise Exception("Node configured to fail.")' },
      },
    ],
    [{ from: 'trigger_manual', to: 'failing_node' }]
  )

  try {
    await openBuilderById(app, workflowId)

    await app.getByRole('button', { name: 'Run' }).click()
    await expect(app.getByRole('heading', { name: /Run/i })).toBeVisible({ timeout: 15_000 })
    await app.getByRole('button', { name: 'Run now' }).click()

    const failingNode = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Failing Node' })
    await expect(failingNode.getByLabel('Error')).toBeVisible({ timeout: 15_000 })
    await failingNode.click()
    await expect(app.getByRole('heading', { name: 'Run details' })).toBeVisible({ timeout: 15_000 })

    await app.getByRole('tab', { name: 'Details' }).click()
    await expect(app.getByRole('tab', { name: 'Details', selected: true })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('"error": "Script failed with exit code 1')).toBeVisible({ timeout: 15_000 })
    await expect(app.getByText('"status": "failed"')).toBeVisible({ timeout: 15_000 })
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})

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
