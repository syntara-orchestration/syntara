/**
 * E2E Tests: Core Stall Detection Behavior
 *
 * Consolidates coverage for:
 * - Live stall warning appearance during workflow execution
 * - Stall visibility in executions list
 * - Stall history persistence after completion (permanent marker semantics)
 * - WebSocket live updates without page refresh
 *
 * All four scenarios share one workflow lifecycle (one stall wait) to minimize runtime.
 */

import { test, expect, toAppUrl } from './fixtures'
import {
  createWorkflowWithStallingActivityViaApi,
  waitForActivityStallWarning,
  waitForExecutionDelayedBadge,
  assertNoStallWarning,
  assertNoExecutionDelayedBadge,
  waitForExecutionCompleted,
  runWorkflowFromBuilderAndCaptureUrl,
} from './helpers/stall-detection'
import { pageHeader } from './helpers/workflow-run'
import { buildUniqueName, waitForUIReady } from './helpers/workflows'
import { deleteWorkflowViaApi } from './utils/api'

test.skip(
  !process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'],
  'Stall detection requires Temporal worker (real backend only)'
)

test.describe('Stall detection core behavior', () => {
  test('stall detection across all views', async ({ app }) => {
    // Setup: Create workflow with stalling activity
    const workflowName = buildUniqueName('stall-test')
    const { id } = await createWorkflowWithStallingActivityViaApi(
      app,
      workflowName,
      3, // expected_duration: 3 seconds
      30 // actual sleep: 30 seconds
    )

    try {
      // Navigate to builder and run workflow
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await waitForUIReady(app)

      // Run workflow and capture execution detail URL
      const executionUrl = await runWorkflowFromBuilderAndCaptureUrl(app)
      await waitForUIReady(app)

      // Assert: Activity is running (no stall yet) — proves WebSocket will deliver change
      await expect(app.getByText('Activity 1')).toBeVisible({ timeout: 15_000 })
      await assertNoStallWarning(app, 'Activity 1')
      await assertNoExecutionDelayedBadge(pageHeader(app))

      // Wait for stall detection (WebSocket patch delivered live)
      // Backend scans every 10s, allow 30s for detection + WebSocket delivery
      await waitForActivityStallWarning(app, 'Activity 1', 30_000)

      // Assert: Stall warning visible in execution detail page header
      await waitForExecutionDelayedBadge(pageHeader(app), 5_000)

      // Assert: Stall warning visible in executions list
      await app.goto(toAppUrl('/executions'))
      await waitForUIReady(app)
      const executionRow = app.getByRole('row').filter({ hasText: workflowName })
      await waitForExecutionDelayedBadge(executionRow, 5_000)

      // Navigate back to execution detail
      await app.goto(executionUrl)
      await waitForUIReady(app)

      // Wait for workflow to complete
      await waitForExecutionCompleted(app, 60_000)

      // Assert: Stall warning persists after completion (permanent marker)
      await expect(pageHeader(app).getByText('Delayed')).toBeVisible()
      await expect(app.getByRole('row').filter({ hasText: 'Activity 1' }).getByText('Stalled')).toBeVisible()

      // Assert: Persistence in executions list
      await app.goto(toAppUrl('/executions'))
      await waitForUIReady(app)
      await expect(app.getByRole('row').filter({ hasText: workflowName }).getByText('Delayed')).toBeVisible()
    } finally {
      // Cleanup
      await deleteWorkflowViaApi(app, id)
    }
  })
})
