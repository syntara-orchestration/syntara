/**
 * E2E Tests: Global Expected Duration Settings
 *
 * Validates that workflows inherit global expected_duration settings
 * when no per-node override is specified.
 *
 * **Real backend only:** Stall detection requires the Temporal worker's periodic
 * stall scanner. The mock API marks activities as completed immediately and does
 * not emit stall/WebSocket updates.
 *
 * **Process-wide state mutation:** This test updates a global runtime setting
 * that affects all concurrent workflow executions. Serial mode prevents races
 * within this file, but parallel workers may observe the temporary setting.
 * For full isolation, run with: `npm run e2e -- stall-detection-global-settings.spec.ts --workers=1`
 */

import { test, expect, toAppUrl } from './fixtures'
import {
  createWorkflowWithoutExpectedDurationViaApi,
  waitForActivityStallWarning,
  waitForExecutionDelayedBadge,
  runWorkflowFromBuilderAndCaptureUrl,
} from './helpers/stall-detection'
import { pageHeader } from './helpers/workflow-run'
import { buildUniqueName, waitForUIReady } from './helpers/workflows'
import { deleteWorkflowViaApi, getSettingViaApi, updateSettingViaApi } from './utils/api'

const SETTING_KEY = 'workflow_engine.script_expected_duration_seconds'

test.skip(
  !process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'],
  'Stall detection requires Temporal worker (real backend only)'
)

test.describe('Stall detection global settings', () => {
  // Serial execution prevents concurrent mutation of the same global setting
  test.describe.configure({ mode: 'serial' })

  test('workflow inherits global expected_duration', async ({ app }) => {
    let originalValue: number | string | boolean | null = null
    let originalVersion: number | undefined
    let defaultValue: number | string | boolean | null = null

    try {
      // Read current setting value and version for cleanup
      const current = await getSettingViaApi(app, SETTING_KEY)
      originalValue = current.value
      originalVersion = current.version
      defaultValue = current.default_value

      // Set global expected duration to 3 seconds
      await updateSettingViaApi(app, SETTING_KEY, 3)

      // Create workflow without expected_duration override
      // The workflow will inherit the global setting
      const workflowName = buildUniqueName('global-setting-test')
      const { id } = await createWorkflowWithoutExpectedDurationViaApi(
        app,
        workflowName,
        30 // actual sleep: 30 seconds
      )

      try {
        // Navigate to builder and run workflow
        await app.goto(toAppUrl(`/workflow-builder/${id}`))
        await waitForUIReady(app)

        // Run workflow and capture execution detail URL
        await runWorkflowFromBuilderAndCaptureUrl(app)
        await waitForUIReady(app)

        // Wait for stall warning to appear
        // The fact that the activity stalls proves:
        // 1. The backend loaded the updated global setting (3s expected duration)
        // 2. The workflow inherited it (no per-node override)
        // 3. The periodic worker detected the stall (30s actual > 3s expected)
        // 4. The WebSocket patch delivered the stall state to the UI
        // Timeout: 60s to allow cache propagation (60s TTL) + stall detection (10s scan interval)
        await waitForActivityStallWarning(app, 'Activity 1', 70_000)

        // Assert: ExecutionDelayedBadge in page header
        await waitForExecutionDelayedBadge(pageHeader(app), 5_000)

        // Assert: Stall warning text label on activity row
        await expect(app.getByRole('row').filter({ hasText: 'Activity 1' }).getByText('Stalled')).toBeVisible()
      } finally {
        // Cleanup workflow
        await deleteWorkflowViaApi(app, id)
      }
    } finally {
      // Restore original setting value using latest version
      // If original value was null (the default), restore to default value to avoid HTTP 422
      if (originalVersion !== undefined) {
        const latest = await getSettingViaApi(app, SETTING_KEY)
        const restoreValue = originalValue ?? defaultValue
        if (restoreValue !== null) {
          await updateSettingViaApi(app, SETTING_KEY, restoreValue, latest.version)
        }
      }
    }
  })
})
