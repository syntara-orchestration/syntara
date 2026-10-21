/**
 * E2E Tests: Builder Execution Panel + Accessibility
 *
 * Validates:
 * - Stall warning visibility in builder execution detail panel
 * - Accessibility compliance of stall UI components
 */

import AxeBuilder from '@axe-core/playwright'

import { test, expect, toAppUrl } from './fixtures'
import {
  createWorkflowWithStallingActivityViaApi,
  waitForActivityStallWarning,
  waitForExecutionDelayedBadge,
  runWorkflowFromBuilderAndCaptureUrl,
} from './helpers/stall-detection'
import { pageHeader } from './helpers/workflow-run'
import { buildUniqueName, waitForUIReady } from './helpers/workflows'
import { deleteWorkflowViaApi } from './utils/api'

test.describe('Stall detection builder and accessibility', () => {
  test('builder execution panel shows delayed badge and passes a11y scan', async ({ app }) => {
    // Setup: Create workflow with stalling activity
    const workflowName = buildUniqueName('builder-a11y-test')
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

      // Wait for stall detection
      await waitForActivityStallWarning(app, 'Activity 1', 30_000)

      // Navigate back to builder to test execution panel
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await waitForUIReady(app)

      // Open execution detail panel (click on execution in history list)
      // The execution history list is on the right side of the builder
      // Click the link within the list item to open the execution details
      const historyLink = app.getByRole('link', { name: new RegExp(workflowName) })
      await expect(historyLink).toBeVisible({ timeout: 15_000 })
      await historyLink.click()

      // Wait for panel to appear
      await expect(app.getByRole('heading', { name: /execution/i })).toBeVisible({ timeout: 10_000 })

      // Assert: ExecutionDelayedBadge appears in panel
      // Panel content is in the drawer region
      const panel = app.getByRole('region').filter({ has: app.getByRole('heading', { name: /execution/i }) })
      await waitForExecutionDelayedBadge(panel, 5_000)

      // Assert: Stall warning label on stalled activity in panel's activity table
      await expect(panel.getByRole('row').filter({ hasText: 'Activity 1' }).getByText('Stalled')).toBeVisible()

      // Navigate to execution detail page for a11y scan
      await app.goto(executionUrl)
      await waitForUIReady(app)

      // Wait for stall UI to be fully rendered
      await expect(pageHeader(app).getByText('Delayed')).toBeVisible()

      // Run accessibility scan
      const results = await new AxeBuilder({ page: app }).analyze()

      // Assert: No new a11y violations
      expect(results.violations).toEqual([])

      // Assert: Stall warning text label is visible
      await expect(app.getByRole('row').filter({ hasText: 'Activity 1' }).getByText('Stalled')).toBeVisible()

      // Assert: ExecutionDelayedBadge has accessible text
      const delayedBadge = pageHeader(app).getByText('Delayed')
      await expect(delayedBadge).toBeVisible()
    } finally {
      // Cleanup
      await deleteWorkflowViaApi(app, id)
    }
  })
})
