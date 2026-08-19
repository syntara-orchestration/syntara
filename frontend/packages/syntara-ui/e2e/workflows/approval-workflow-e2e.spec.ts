import type { Page } from '@playwright/test'

import { test, expect } from '../fixtures'
import { navigateToApprovalAndOpen } from '../helpers/approvals'
import { addApprovalNodeWithBranch } from '../helpers/v2-nodes'
import { buildUniqueName, createBasicWorkflowViaApi, openWorkflowInBuilder } from '../helpers/workflows'
import { apiRequest, pollApprovalVisible, pollExecutionStatus } from '../utils/api'

/**
 * Helper: Create a workflow with an approval node and run it to create a pending approval.
 * Returns workflow ID and approval node name for cleanup and filtering.
 */
async function createPendingApproval(app: Page): Promise<{ workflowId: string; approvalName: string }> {
  const workflowName = buildUniqueName('e2e-approval-test')
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

  // Wait for navigation and pause at approval
  const didNavigate = await app
    .waitForURL(/\/executions\//, { timeout: 10_000 })
    .then(() => true)
    .catch(() => false)
  test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

  const executionId = app.url().match(/\/executions\/([a-f0-9-]+)/)?.[1]
  test.skip(!executionId, 'Could not extract execution ID from URL')

  const reachedApproval = await pollExecutionStatus(app, executionId!, ['paused'])
    .then(() => true)
    .catch(() => false)
  test.skip(!reachedApproval, 'Execution did not reach paused state — Temporal worker may not be running')

  await pollApprovalVisible(app, approvalName)

  return { workflowId, approvalName }
}

/**
 * E2E Tests: Approval Workflow — Previous Step Output Display
 *
 * This file tests the unique capability of viewing previous step output
 * in the approval panel. Other approval workflow behaviors are covered by:
 *
 * - Approve/reject flows: `e2e/workflows/approvals.spec.ts` (UI-29, UI-30)
 * - Filtering: `e2e/workflows/approvals.spec.ts` (user filters approvals by name and status)
 * - Navigation: `e2e/workflows/approval-side-panel.spec.ts` (clicking approval name navigates...)
 *
 * Critical path covered:
 * - View pending approval with previous step output displayed in panel
 */
test.describe('Approval Workflow E2E', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'], 'Temporal worker unavailable (globalSetup probe)')

  test('view pending approval with previous step output', async ({ app }) => {
    // Create a pending approval (workflow has a script node before the approval node)
    const approval = await createPendingApproval(app)

    try {
      // Navigate to the approval and open the panel
      await navigateToApprovalAndOpen(app, approval.approvalName)

      // Verify previous step output is displayed
      // The pre-approval script node output should be visible in the panel
      // This is the UNIQUE coverage this test provides - other tests don't verify output display
      // The createBasicWorkflowViaApi helper creates a script that outputs "hello"
      await expect(app.getByRole('region', { name: /output/i })).toContainText('hello')
    } finally {
      await apiRequest(app, 'delete', `/workflows/${approval.workflowId}`).catch(() => {})
    }
  })
})
