/**
 * E2E Tests: Global Expected Duration Settings
 *
 * Validates that workflows inherit global expected_duration settings
 * when no per-node override is specified.
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

test.describe('Stall detection global settings', () => {
  test('workflow inherits global expected_duration', async ({ app }) => {
    let originalValue: number | string | boolean | null = null

    try {
      // Read current setting value for cleanup
      const current = await getSettingViaApi(app, SETTING_KEY)
      originalValue = current.value

      // Set global expected duration to 3 seconds
      await updateSettingViaApi(app, SETTING_KEY, 3)

      // Wait 60s for settings cache to propagate
      // Settings cache TTL is 60s by default
      await app.waitForTimeout(60_000)

      // Create workflow without expected_duration override
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

        // Wait for stall warning to appear (proves global setting was inherited)
        await waitForActivityStallWarning(app, 'Activity 1', 30_000)

        // Assert: ExecutionDelayedBadge in page header
        await waitForExecutionDelayedBadge(pageHeader(app), 5_000)

        // Assert: Stall warning text label on activity row
        await expect(app.getByRole('row').filter({ hasText: 'Activity 1' }).getByText('Stalled')).toBeVisible()
      } finally {
        // Cleanup workflow
        await deleteWorkflowViaApi(app, id)
      }
    } finally {
      // Restore original setting value
      if (originalValue !== null) {
        await updateSettingViaApi(app, SETTING_KEY, originalValue)
      } else {
        // Setting was null (disabled), restore by setting to null
        await updateSettingViaApi(app, SETTING_KEY, null)
      }
    }
  })
})
