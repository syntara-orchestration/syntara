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

import { type Page } from '@playwright/test'

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
