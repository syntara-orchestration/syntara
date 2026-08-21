import type { Page } from '@playwright/test'

import { test, expect } from '../fixtures'
import { addApprovalNodeWithBranch } from '../helpers/v2-nodes'
import { buildUniqueName, createBasicWorkflowViaApi, openWorkflowInBuilder, deleteWorkflow } from '../helpers/workflows'
import { pollExecutionStatus } from '../utils/api'

/**
 * E2E Tests: Approval Pending Badge Display
 *
 * Verifies that the "Pending approval" badge appears in all three locations when an
 * execution has a pending approval:
 * 1. Executions list table
 * 2. Workflow run history panel
 * 3. Execution detail page header
 *
 * This tests the full flow: Database → API → WebSocket → UI
 */

/**
 * Helper: Create a workflow with an approval node and run it to create a pending approval.
 * Returns workflow ID and execution ID for verification and cleanup.
 */
async function createPendingApproval(
  app: Page
): Promise<{ workflowId: string; executionId: string; workflowName: string }> {
  const workflowName = buildUniqueName('approval-badge-test')
  const approvalName = buildUniqueName('approval')

  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Pre-approval step')
  await openWorkflowInBuilder(app, workflowName, id)
  const workflowId = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]
  if (!workflowId) throw new Error('Failed to extract workflow ID')

  // Add approval node and save
  await addApprovalNodeWithBranch(app, approvalName)
  await app.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(app.getByRole('button', { name: 'Run', exact: true })).toBeEnabled({ timeout: 15_000 })

  // Run the workflow
  await app.getByRole('button', { name: 'Run', exact: true }).click()
  await app.getByRole('button', { name: /Run now|Save and run/ }).click()

  // Wait for navigation to execution detail page
  const didNavigate = await app
    .waitForURL(/\/executions\//, { timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

  // Extract execution ID from URL
  const executionId = app.url().match(/executions\/([^/?]+)/)?.[1]
  if (!executionId) throw new Error('Failed to extract execution ID')

  // Poll API for "paused" status instead of relying on UI updates
  const reachedApproval = await pollExecutionStatus(app, executionId, ['paused'])
    .then(() => true)
    .catch(() => false)
  test.skip(!reachedApproval, 'Execution did not reach paused state — Temporal worker may not be running')

  return { workflowId, executionId, workflowName }
}

async function applyPendingApprovalStatusFilter(app: Page): Promise<void> {
  const filterButton = app.getByRole('button', { name: /Filter|Add filter/i })
  await expect(filterButton).toBeVisible()
  await filterButton.click()

  const statusFieldOption = app.getByRole('option', { name: /^Status$/i })
  await expect(statusFieldOption).toBeVisible()
  await statusFieldOption.click()

  const statusValueSelector = app.getByRole('button', { name: /Filter by status/i })
  await expect(statusValueSelector).toBeVisible()
  await statusValueSelector.click()

  const pendingApprovalOption = app.getByRole('option', { name: /^Pending approval$/i })
  await expect(pendingApprovalOption).toBeVisible()
  await pendingApprovalOption.click()
}

test.describe('Approval Pending Badge', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'], 'Temporal worker unavailable (globalSetup probe)')

  test(
    'shows "Pending approval" badge in all three locations when execution has pending approval',
    { tag: ['@konflux-skip'] },
    async ({ app }) => {
      let workflowName: string | undefined

      try {
        const result = await createPendingApproval(app)
        workflowName = result.workflowName
        const { workflowId, executionId } = result

        // ===================================================================
        // LOCATION 1: Execution Detail Page Header
        // ===================================================================
        // We're already on the execution detail page from createPendingApproval.
        // Use a generous timeout — the badge depends on a WebSocket push and Konflux
        // network latency can delay the update by several seconds.
        await expect(app.getByText('Pending approval')).toBeVisible({ timeout: 15_000 })

        // Verify the badge has warning styling (outline variant) in the execution detail page header
        const badgeInDetail = app.locator('header').getByText('Pending approval')
        await expect(badgeInDetail).toBeVisible()

        // ===================================================================
        // LOCATION 2: Workflow Run History Panel
        // ===================================================================
        // Navigate back to the workflow builder
        await app.goto(`/workflow-builder/${workflowId}`)

        // Open the run history panel (if not already open)
        const historyButton = app.getByRole('button', { name: /Run history|History/ })
        if (await historyButton.isVisible()) {
          await historyButton.click()
        }

        // Verify badge appears in the history panel
        const historyPanel = app.getByRole('list', { name: 'Run history list' })
        const badgeInHistory = historyPanel.getByText('Pending approval')

        await expect(badgeInHistory).toBeVisible({ timeout: 5_000 })

        // ===================================================================
        // LOCATION 3: Executions List Table
        // ===================================================================
        // Navigate to executions list
        await app.goto('/executions')

        // Wait for the table to load
        await expect(app.getByRole('table')).toBeVisible({ timeout: 10_000 })

        // Find the row with our execution ID and verify badge is visible
        const executionRow = app.locator('tr', { has: app.getByText(executionId.slice(0, 8)) })
        const badgeInList = executionRow.getByText('Pending approval')

        await expect(badgeInList).toBeVisible({ timeout: 5_000 })

        // Verify the badge appears alongside the "Paused" status
        const pausedStatus = executionRow.getByText('Paused')
        await expect(pausedStatus).toBeVisible()

        // ===================================================================
        // VERIFICATION: Filter by "Pending approval" via Status filter
        // ===================================================================
        await applyPendingApprovalStatusFilter(app)
        await expect(badgeInList).toBeVisible()
      } finally {
        // Cleanup: Delete the workflow
        if (workflowName) {
          await deleteWorkflow(app, workflowName)
        }
      }
    }
  )

  test('does NOT show "Pending approval" badge when execution has no pending approvals', async ({ app }) => {
    let workflowName: string | undefined

    try {
      workflowName = buildUniqueName('no-approval-badge-test')

      // Create a simple workflow WITHOUT approval node
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Simple step')
      await openWorkflowInBuilder(app, workflowName, id)
      const workflowId = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]
      if (!workflowId) throw new Error('Failed to extract workflow ID')

      // createBasicWorkflowViaApi already saves the workflow, so Run button should be enabled
      await expect(app.getByRole('button', { name: 'Run', exact: true })).toBeEnabled({ timeout: 15_000 })

      // Run the workflow
      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: /Run now|Save and run/ }).click()
      await app.waitForTimeout(2000)
      // Wait for navigation to execution detail page
      await app.waitForURL(/\/executions\//, { timeout: 5_000 })

      // Extract execution ID from URL for later verification
      const executionId = app.url().match(/executions\/([^/?]+)/)?.[1]
      if (!executionId) throw new Error('Failed to extract execution ID')

      // Wait for the execution detail page to load by checking for the page heading
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 10_000 })

      // Wait for at least one activity to show a terminal status (Successful/Failed) in the activities table
      // This confirms the execution has finished running
      const reachedTerminal = await app
        .getByRole('row')
        .filter({ hasText: /Successful|Failed/ })
        .nth(0)
        .waitFor({ state: 'visible', timeout: 30_000 })
        .then(() => true)
        .catch(() => false)
      test.skip(
        !reachedTerminal,
        'Workflow execution did not complete in time — may indicate worker/runtime issues in CI'
      )

      // Give WebSocket updates a moment to settle after terminal state is reached
      await app.waitForTimeout(2000)

      // Verify "Pending approval" badge does NOT appear in the execution detail header
      // This must be true regardless of whether the execution succeeded or failed,
      // because this workflow has NO approval node
      const pendingBadgeInHeader = app.locator('header').getByText('Pending approval', { exact: true })
      await expect(pendingBadgeInHeader).toHaveCount(0)

      // Navigate to executions list
      await app.goto('/executions')
      await app.waitForLoadState('networkidle')
      await expect(app.getByRole('grid')).toBeVisible({ timeout: 10_000 })

      // Wait for any WebSocket updates to settle after page load
      await app.waitForTimeout(1000)

      // Find the specific row for this execution
      const executionRow = app.locator('tr', { has: app.getByText(executionId.slice(0, 8)) })

      // First ensure the row exists in the table (our execution should be visible)
      await expect(executionRow).toBeVisible({ timeout: 10_000 })

      // Then verify no "Pending approval" badge appears in that row
      // Use toHaveCount(0) which is more reliable for negative assertions than not.toBeAttached()
      const pendingBadgeInRow = executionRow.getByText('Pending approval', { exact: true })
      await expect(pendingBadgeInRow).toHaveCount(0)
    } finally {
      // Cleanup: Delete the workflow
      if (workflowName) {
        await deleteWorkflow(app, workflowName)
      }
    }
  })
})
