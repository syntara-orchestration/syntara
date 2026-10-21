/**
 * Stall detection E2E test helpers.
 * Provides utilities for creating workflows with stall-triggering activities and asserting on stall UI state.
 */
import type { Locator } from '@playwright/test'

import { type Page, expect } from '../fixtures'
import { createWorkflowViaApi } from '../utils/api'

import { runWorkflowFromBuilder } from './workflow-run'

/**
 * Create a workflow with a script activity configured to stall.
 * @param app - Page fixture
 * @param workflowName - Unique workflow name
 * @param expectedDuration - Expected duration in seconds (e.g., 3)
 * @param actualDuration - Actual sleep duration in seconds (e.g., 30)
 */
export async function createWorkflowWithStallingActivityViaApi(
  app: Page,
  workflowName: string,
  expectedDuration: number,
  actualDuration: number
): Promise<{ id: string }> {
  const { id } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: 'activity_1',
        type: 'script',
        name: 'Activity 1',
        parameters: {
          language: 'python',
          code: `import time\ntime.sleep(${actualDuration})`,
        },
        settings: {
          expected_duration: expectedDuration,
        },
      },
    ],
    edges: [{ from: 'trigger_1', to: 'activity_1' }],
  })
  return { id }
}

/**
 * Create a workflow with a script activity that completes quickly (no stall).
 * @param app - Page fixture
 * @param workflowName - Unique workflow name
 * @param expectedDuration - Expected duration in seconds (e.g., 60)
 * @param actualDuration - Actual sleep duration in seconds (e.g., 2)
 */
export async function createWorkflowWithFastActivityViaApi(
  app: Page,
  workflowName: string,
  expectedDuration: number,
  actualDuration: number
): Promise<{ id: string }> {
  const { id } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: 'activity_1',
        type: 'script',
        name: 'Activity 1',
        parameters: {
          language: 'python',
          code: `import time\ntime.sleep(${actualDuration})`,
        },
        settings: {
          expected_duration: expectedDuration,
        },
      },
    ],
    edges: [{ from: 'trigger_1', to: 'activity_1' }],
  })
  return { id }
}

/**
 * Create a workflow with a script activity without expected_duration override.
 * Used to test global expected_duration fallback.
 */
export async function createWorkflowWithoutExpectedDurationViaApi(
  app: Page,
  workflowName: string,
  actualDuration: number
): Promise<{ id: string }> {
  const { id } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: 'activity_1',
        type: 'script',
        name: 'Activity 1',
        parameters: {
          language: 'python',
          code: `import time\ntime.sleep(${actualDuration})`,
          // No expected_duration — should inherit global setting
        },
      },
    ],
    edges: [{ from: 'trigger_1', to: 'activity_1' }],
  })
  return { id }
}

/**
 * Poll for stall warning label on an activity row.
 * Scoped to the activity row to avoid false matches.
 */
export async function waitForActivityStallWarning(app: Page, activityName: string, timeout = 30_000): Promise<void> {
  const activityRow = app.getByRole('row').filter({ hasText: activityName })
  // Look for "Stalled" text label in the activity row
  await expect(activityRow.getByText('Stalled')).toBeVisible({ timeout })
}

/**
 * Poll for "Delayed" badge in specified scope (page header, list row, panel header).
 * @param locatorScope - Parent locator to scope the search
 */
export async function waitForExecutionDelayedBadge(locatorScope: Locator, timeout = 10_000): Promise<void> {
  await expect(locatorScope.getByText('Delayed')).toBeVisible({ timeout })
}

/**
 * Assert that no stall warning label is present on an activity row.
 */
export async function assertNoStallWarning(app: Page, activityName: string): Promise<void> {
  const activityRow = app.getByRole('row').filter({ hasText: activityName })
  await expect(activityRow.getByText('Stalled')).toHaveCount(0, { timeout: 2_000 })
}

/**
 * Assert that no "Delayed" badge is present in specified scope.
 */
export async function assertNoExecutionDelayedBadge(locatorScope: Locator): Promise<void> {
  await expect(locatorScope.getByText('Delayed')).toHaveCount(0, { timeout: 2_000 })
}

/**
 * Poll for execution status "Completed".
 * Uses page header status badge.
 */
export async function waitForExecutionCompleted(app: Page, timeout = 60_000): Promise<void> {
  // Wait for "Completed" status in the execution status badge in page header
  const { pageHeader } = await import('./workflow-run')
  await expect(pageHeader(app).getByText('Completed')).toBeVisible({ timeout })
}

/**
 * Run workflow from builder and capture the execution detail URL.
 * Returns URL string for later navigation.
 */
export async function runWorkflowFromBuilderAndCaptureUrl(app: Page): Promise<string> {
  await runWorkflowFromBuilder(app)
  // Capture the current URL (should be /executions/{id})
  return app.url()
}
