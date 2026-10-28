/**
 * E2E Tests: No False Positives for Fast Activities
 *
 * Validates that activities completing within their expected duration
 * do not trigger stall warnings.
 *
 * **Real backend only:** Stall detection requires the Temporal worker's periodic
 * stall scanner. The mock API marks activities as completed immediately and does
 * not emit stall/WebSocket updates.
 */

import { test, expect, toAppUrl } from './fixtures'
import {
  createWorkflowWithFastActivityViaApi,
  assertNoStallWarning,
  assertNoExecutionDelayedBadge,
  runWorkflowFromBuilderAndCaptureUrl,
} from './helpers/stall-detection'
import { pageHeader } from './helpers/workflow-run'
import { buildUniqueName, waitForUIReady } from './helpers/workflows'
import { deleteWorkflowViaApi } from './utils/api'

test.skip(
  !process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'],
  'Stall detection requires Temporal worker (real backend only)'
)

// Skip in Konflux: stall detection timing is too fragile under cluster load.
// Periodic worker scans (10s interval) + execution startup + WebSocket propagation
// can exceed test timeouts when Konflux infrastructure is under load.
test.skip(!!process.env['KUBERNETES_SERVICE_HOST'], 'Stall detection timing too fragile under Konflux cluster load')

test.describe('Stall detection false positives', () => {
  test('activity below threshold not flagged', async ({ app }) => {
    // Setup: Create workflow with fast activity
    const workflowName = buildUniqueName('no-stall-test')
    const { id } = await createWorkflowWithFastActivityViaApi(
      app,
      workflowName,
      60, // expected_duration: 60 seconds
      2 // actual sleep: 2 seconds (completes well within threshold)
    )

    try {
      // Navigate to builder and run workflow
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await waitForUIReady(app)

      // Run workflow and capture execution detail URL
      await runWorkflowFromBuilderAndCaptureUrl(app)
      await waitForUIReady(app)

      // Wait for Activity 1 to complete
      // Activity sleeps for 2 seconds, but allow time for execution startup and Temporal processing
      await expect(pageHeader(app).getByText('Completed')).toBeVisible({ timeout: 60_000 })

      // Wait 15s to allow at least one worker scan cycle
      await app.waitForTimeout(15_000)

      // Assert: No stall warning icon on Activity 1 row
      await assertNoStallWarning(app, 'Activity 1')

      // Assert: No ExecutionDelayedBadge in page header
      await assertNoExecutionDelayedBadge(pageHeader(app))

      // Assert: No ExecutionDelayedBadge in executions list
      await app.goto(toAppUrl('/executions'))
      await waitForUIReady(app)
      const executionRow = app.getByRole('row').filter({ hasText: workflowName })
      await assertNoExecutionDelayedBadge(executionRow)
    } finally {
      // Cleanup
      await deleteWorkflowViaApi(app, id)
    }
  })
})
