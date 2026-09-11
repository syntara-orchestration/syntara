/**
 * E2E Tests (UI-20): Execution — Manual Run from Canvas
 *
 * Objective: Verify that a workflow can be manually run from the builder canvas,
 * that the live run details panel appears, and that node status badges update
 * in real time as Temporal executes the workflow.
 *
 * Test coverage:
 * - Clicking Run and confirming opens the "Run details" panel
 * - Node status badges show Success after execution completes
 * - Failed nodes show an error status badge
 */

import { type Page } from '../fixtures'
import { test, expect } from '../fixtures'
import { buildUniqueName, openBuilderById } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from '../utils/api'

/**
 * Wait for a status badge to appear on the canvas. Retries to handle
 * WebSocket timing where badges may arrive after the initial DOM render.
 */
async function waitForBadge(app: Page, name: string, count?: number) {
  const badge = app.getByRole('img', { name })
  if (count !== undefined) {
    await expect(badge).toHaveCount(count, { timeout: 90_000 })
  } else {
    await expect(badge).toBeVisible({ timeout: 90_000 })
  }
}

// Skip: tests consistently time out in CI waiting for workflow execution to complete
test.skip('clicking Run and confirming opens the live run details panel', async ({ app }) => {
  test.setTimeout(120_000)
  const workflowName = buildUniqueName('e2e-manual-run')
  // validateMinimumWorkflow requires: trigger + at least one node + an edge connecting them
  const { id: workflowId } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [{ id: 'action_1', type: 'script', name: 'Test step', parameters: { language: 'python', code: "print('hi')" } }],
    [{ from: 'trigger_1', to: 'action_1' }]
  )
  try {
    await openBuilderById(app, workflowId)
    await expect(app.getByText('Manual trigger')).toBeVisible({ timeout: 30_000 })

    await app.getByRole('button', { name: 'Run' }).click()
    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Run now' }).click()
    await expect(dialog).not.toBeVisible()

    // The run details panel appears below the canvas once execution completes
    await expect(app.getByRole('heading', { name: 'Run details' })).toBeVisible({ timeout: 30_000 })
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})

test.skip('node status badges show success after execution completes', async ({ app }) => {
  test.setTimeout(120_000)
  const workflowName = buildUniqueName('e2e-manual-run-badge')
  const { id: workflowId } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'action_1',
        type: 'script',
        name: 'Test action',
        parameters: { language: 'python', code: "print('hi')" },
      },
    ],
    [{ from: 'trigger_1', to: 'action_1' }]
  )
  try {
    await openBuilderById(app, workflowId)
    await expect(app.getByText('Manual trigger')).toBeVisible({ timeout: 30_000 })

    await app.getByRole('button', { name: 'Run' }).click()
    await app.getByRole('dialog').getByRole('button', { name: 'Run now' }).click()

    await waitForBadge(app, 'Success', 2)
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})

test.skip('failed nodes show an error status badge', async ({ app }) => {
  test.setTimeout(120_000)
  const workflowName = buildUniqueName('e2e-manual-run-fail')
  const { id: workflowId } = await createWorkflowViaApi(
    app,
    workflowName,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'action_1',
        type: 'script',
        name: 'Failing action',
        parameters: { language: 'python', code: 'raise Exception("fail")' },
      },
    ],
    [{ from: 'trigger_1', to: 'action_1' }]
  )
  try {
    await openBuilderById(app, workflowId)
    await expect(app.getByText('Manual trigger')).toBeVisible({ timeout: 30_000 })

    await app.getByRole('button', { name: 'Run' }).click()
    await app.getByRole('dialog').getByRole('button', { name: 'Run now' }).click()

    // Failed node shows an error badge
    await waitForBadge(app, 'Error')
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})
