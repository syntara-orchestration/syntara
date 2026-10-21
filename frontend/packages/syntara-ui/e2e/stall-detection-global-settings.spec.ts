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
  // Serial execution prevents concurrent mutation of the same global setting
  test.describe.configure({ mode: 'serial' })

  test('workflow inherits global expected_duration', async ({ app }) => {
    let originalValue: number | string | boolean | null = null
    let originalVersion: number | undefined

    try {
      // Read current setting value and version for cleanup
      const current = await getSettingViaApi(app, SETTING_KEY)
      originalValue = current.value
      originalVersion = current.version

      // Set global expected duration to 3 seconds
      const { version: newVersion } = await updateSettingViaApi(app, SETTING_KEY, 3)

      // Poll for setting propagation instead of fixed wait
      // Backend settings cache uses a 60s TTL, but propagation may be faster
      await expect
        .poll(
          async () => {
            const latest = await getSettingViaApi(app, SETTING_KEY)
            return latest.version >= newVersion && latest.value === 3
          },
          {
            message: 'Setting update did not propagate',
            timeout: 65_000,
            intervals: [5_000, 10_000],
          }
        )
        .toBe(true)

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
      // Restore original setting value using latest version
      if (originalVersion !== undefined) {
        const latest = await getSettingViaApi(app, SETTING_KEY)
        await updateSettingViaApi(app, SETTING_KEY, originalValue, latest.version)
      }
    }
  })
})
