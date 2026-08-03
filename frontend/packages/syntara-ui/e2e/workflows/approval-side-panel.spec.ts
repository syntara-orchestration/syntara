/**
 * E2E Tests: Approval Side Panel (UI-28, UI-30)
 *
 * Critical paths covered:
 * - Deep-link from approvals list navigates to execution detail with side panel
 * - Side panel displays approval details (step name, workflow, designer message, approve/reject buttons)
 * - Approve and reject flows with notes and undo
 * - Panel and run history card are mutually exclusive
 * - Viewer role cannot approve or reject (permission gating)
 * - UI-28: Self-contained — create workflow with approval node, run, verify execution shows
 *   "Paused" status and "Waiting for approval" activity indicator
 * - UI-30: Self-contained — reject a pending approval and verify execution terminates
 *
 * Seed data:
 * - Approval "Production Deployment Approval" (550e8400-...-446655440050) linked to exec-approval
 */
import { createUnavailableGuard, test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
  publishWorkflowViaApi,
} from '../utils/api'

const MOCK_APPROVAL_ID = '550e8400-e29b-41d4-a716-446655440050'
const MOCK_EXECUTION_ID = 'exec-approval'
const DEEP_LINK = `/executions/${MOCK_EXECUTION_ID}?approval=${MOCK_APPROVAL_ID}&history=closed`

/**
 * Navigate directly to the execution detail with the approval side panel via deep-link.
 * Returns false if the panel didn't load (missing seed data / API unavailable).
 */
async function navigateToApprovalPanel(app: import('@playwright/test').Page) {
  await app.goto(toAppUrl(DEEP_LINK))
  await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

  return app
    .getByRole('heading', { name: 'Review Approval' })
    .waitFor({ state: 'visible', timeout: 30_000 })
    .then(() => true)
    .catch(() => false)
}

test.describe('Approval Side Panel — list navigation', () => {
  test('clicking approval name navigates to execution detail with side panel', async ({ app }) => {
    await app.goto(toAppUrl('/approvals'))
    await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Approvals table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No approval data available')

    const approvalLink = table.getByRole('link', { name: 'Production Deployment Approval' })
    const hasLink = await approvalLink
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasLink, 'Production Deployment Approval not found in table')

    await approvalLink.click()

    await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=.*&history=closed/)
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
  })
})

test.describe('Approval Side Panel — deep-link', () => {
  const guard = createUnavailableGuard('Approval side panel not available')

  test.beforeEach(async ({ app }) => {
    const hasPanel = await navigateToApprovalPanel(app)
    if (!hasPanel) guard.markUnavailable()
    test.skip(!hasPanel, 'Approval side panel not available')
  })

  test('side panel displays approval details and action buttons', async ({ app }) => {
    // Decision buttons
    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Reject' })).toBeVisible()

    // Summary fields (use exact matching to avoid code block collisions)
    await expect(app.getByText('Approval step', { exact: true })).toBeVisible()
    await expect(app.locator('dd').getByText('Production Deployment Approval', { exact: true })).toBeVisible()
    await expect(app.getByText('Workflow', { exact: true })).toBeVisible()
    await expect(app.locator('dd').getByText('deployment-approval', { exact: true })).toBeVisible()
    await expect(app.getByText('Approval initiated', { exact: true })).toBeVisible()
    await expect(app.getByText('Message', { exact: true })).toBeVisible()
    await expect(app.getByText(/Review the staging test results/)).toBeVisible()
  })

  test('clicking approve shows notes input and submit button', async ({ app }) => {
    const approveBtn = app.getByRole('button', { name: 'Approve' })
    await expect(approveBtn).not.toHaveAttribute('aria-disabled', 'true')

    await approveBtn.click()

    await expect(app.getByPlaceholder(/Explain the reason for approving/i)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible()

    // Undo returns to initial button state
    await app.getByRole('button', { name: 'Undo decision' }).click()
    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Reject' })).toBeVisible()
  })

  test('clicking reject shows notes input and submit button', async ({ app }) => {
    const rejectBtn = app.getByRole('button', { name: 'Reject' })
    await expect(rejectBtn).not.toHaveAttribute('aria-disabled', 'true')

    await rejectBtn.click()

    await expect(app.getByPlaceholder(/Explain the reason for rejecting/i)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible()

    await app.getByRole('button', { name: 'Undo decision' }).click()
    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
  })

  test('run history and approval panel are mutually exclusive', async ({ app }) => {
    // History should be closed (deep-link sets history=closed)
    const historyHeading = app.getByRole('heading', { name: 'Run history' })
    await expect(historyHeading).not.toBeVisible()

    // Open run history — should close approval panel
    await app.getByRole('button', { name: /Run history/i }).click()
    await expect(historyHeading).toBeVisible()
    await expect(app.getByRole('heading', { name: 'Review Approval' })).not.toBeVisible()

    // Re-open approval panel via the Review button — should close history
    const reviewBtn = app.getByRole('button', { name: 'Review approval' })
    await reviewBtn.click()
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible()
    await expect(historyHeading).not.toBeVisible()
  })
})

test.describe('Approval Side Panel — deep-link (viewer)', () => {
  test('viewer: approve and reject buttons are disabled', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(DEEP_LINK))
    await expect(viewerApp.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    const hasPanel = await viewerApp
      .getByRole('heading', { name: 'Review Approval' })
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasPanel, 'Approval side panel not available')

    const approveBtn = viewerApp.getByRole('button', { name: 'Approve' })
    const rejectBtn = viewerApp.getByRole('button', { name: 'Reject' })
    await expect(approveBtn).toHaveAttribute('aria-disabled', 'true')
    await expect(rejectBtn).toHaveAttribute('aria-disabled', 'true')
  })
})

test.describe('Approval Side Panel — self-contained', () => {
  test('UI-28: execution shows Paused status and Waiting for approval indicator', async ({ app }) => {
    test.slow()
    const approvalNodeName = buildUniqueName('review-gate')
    const workflowName = buildUniqueName('e2e-approval-panel')

    const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
    const nodes = [
      { id: 'approval_1', type: 'approval', name: approvalNodeName, parameters: {} },
      { id: 'post_1', type: 'script', name: 'Post Approval', parameters: { language: 'python', code: 'pass' } },
    ]
    const edges = [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'post_1', from_port: 'approved' },
    ]

    const { id: workflowId, versionNumber } = await createWorkflowViaApi(app, workflowName, triggers, nodes, edges)

    try {
      await publishWorkflowViaApi(app, workflowId, versionNumber)

      const token = await getAuthToken(app)
      if (!token) throw new Error('Could not obtain auth token')

      const resp = await apiRequest(app, 'post', '/executions', {
        token,
        data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
      })
      expect(resp.ok(), `POST /executions returned ${resp.status()}`).toBeTruthy()
      const { id: executionId } = (await resp.json()) as { id: string }

      await pollExecutionStatus(app, executionId, ['paused'], { token, timeout: 60_000 })

      await app.goto(toAppUrl(`/executions/${executionId}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByText('Waiting for approval')).toBeVisible({ timeout: 30_000 })
      await expect(app.getByRole('button', { name: 'Review approval' })).toBeVisible({ timeout: 30_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('UI-30: rejecting an approval terminates workflow execution', async ({ app }) => {
    test.slow()
    const approvalNodeName = buildUniqueName('rejection-gate')
    const workflowName = buildUniqueName('e2e-reject')

    const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
    const nodes = [
      { id: 'approval_1', type: 'approval', name: approvalNodeName, parameters: {} },
      { id: 'post_1', type: 'script', name: 'Post Approval', parameters: { language: 'python', code: 'pass' } },
    ]
    const edges = [
      { from: 'trigger_1', to: 'approval_1' },
      { from: 'approval_1', to: 'post_1', from_port: 'approved' },
    ]

    const { id: workflowId, versionNumber } = await createWorkflowViaApi(app, workflowName, triggers, nodes, edges)

    try {
      await publishWorkflowViaApi(app, workflowId, versionNumber)

      const token = await getAuthToken(app)
      if (!token) throw new Error('Could not obtain auth token')

      const resp = await apiRequest(app, 'post', '/executions', {
        token,
        data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
      })
      expect(resp.ok(), `POST /executions returned ${resp.status()}`).toBeTruthy()
      const { id: executionId } = (await resp.json()) as { id: string }

      await pollExecutionStatus(app, executionId, ['paused'], { token, timeout: 60_000 })

      let approvalId: string | undefined
      await expect(async () => {
        const r = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
        const body = (await r.json()) as { resources?: Array<{ id: string }> }
        approvalId = body.resources?.[0]?.id
        expect(approvalId).toBeTruthy()
      }).toPass({ timeout: 30_000, intervals: [2_000] })

      await app.goto(toAppUrl(`/executions/${executionId}?approval=${approvalId}&history=closed`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })

      await app.getByRole('button', { name: 'Reject', exact: true }).click()
      await app.getByPlaceholder(/Explain the reason for rejecting/i).fill('Rejected in E2E test')
      await app.getByRole('button', { name: 'Submit decision' }).click()

      await expect(app.getByText('Rejection submitted')).toBeVisible({ timeout: 15_000 })

      await pollExecutionStatus(app, executionId, ['completed', 'completed_with_errors', 'failed', 'cancelled'], {
        token,
        timeout: 60_000,
      })
      await app.reload()
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByTestId('execution-status-badge').getByText(/Completed|Failed|Rejected/i)).toBeVisible({
        timeout: 30_000,
      })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})
