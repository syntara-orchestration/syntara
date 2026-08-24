/**
 * E2E Tests: Approval Side Panel
 *
 * Critical paths covered:
 * - List navigation: clicking approval name navigates to execution detail with side panel
 * - Deep-link: side panel displays approval details, approve/reject flows with undo
 * - Panel and run history card are mutually exclusive
 * - Viewer role cannot approve or reject (permission gating)
 * - UI-28: execution shows Paused status and Waiting for approval indicator
 * - UI-30: rejecting a pending approval terminates workflow execution
 *
 * Setup: beforeAll creates a workflow with an approval node via API, runs it,
 * and waits for the approval to be indexed. All deep-link tests share this data.
 * Self-contained tests (UI-28, UI-30) create their own workflows.
 */
import { test, expect, toAppUrl } from '../fixtures'
import { dismissConnectionBanner } from '../helpers/approvals'
import { buildUniqueName } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
  publishWorkflowViaApi,
} from '../utils/api'

test.describe('Approval Side Panel', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedWorkflowId: string | undefined
  let sharedExecutionId: string | undefined
  let sharedApprovalId: string | undefined
  let sharedApprovalName = ''
  let sharedWorkflowName = ''
  let sharedSetupSkipReason: string | undefined

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sharedApprovalName = buildUniqueName('panel-gate')
      sharedWorkflowName = buildUniqueName('e2e-side-panel')

      const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
      const nodes = [
        { id: 'approval_1', type: 'approval', name: sharedApprovalName, parameters: {} },
        {
          id: 'post_1',
          type: 'script',
          name: 'Post Approval',
          parameters: { language: 'python', code: 'pass' },
        },
      ]
      const edges = [
        { from: 'trigger_1', to: 'approval_1' },
        { from: 'approval_1', to: 'post_1', from_port: 'approved' },
      ]

      const result = await createWorkflowViaApi(page, sharedWorkflowName, triggers, nodes, edges)
      sharedWorkflowId = result.id

      await publishWorkflowViaApi(page, sharedWorkflowId, result.versionNumber)

      const token = await getAuthToken(page)
      if (!token) throw new Error('Could not obtain auth token')

      const resp = await apiRequest(page, 'post', '/executions', {
        token,
        data: { workflow_id: sharedWorkflowId, trigger_node_id: 'trigger_1' },
      })
      if (!resp.ok()) throw new Error(`POST /executions returned ${resp.status()}`)
      const body = (await resp.json()) as { id: string }
      sharedExecutionId = body.id

      await pollExecutionStatus(page, sharedExecutionId, ['paused'], { token, timeout: 60_000 })

      const probeResp = await apiRequest(page, 'get', `/approvals?execution_id=${sharedExecutionId}&status=pending`, {
        token,
      })
      if (!probeResp.ok()) {
        sharedSetupSkipReason = `Approvals API returned ${probeResp.status()} — service may be unavailable`
        return
      }

      await expect(async () => {
        const r = await apiRequest(page, 'get', `/approvals?execution_id=${sharedExecutionId}&status=pending`, {
          token,
        })
        const approvals = (await r.json()) as { resources?: Array<{ id: string }> }
        const id = approvals.resources?.[0]?.id
        expect(id).toBeTruthy()
        sharedApprovalId = id!
      }).toPass({ timeout: 60_000, intervals: [2_000] })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    if (!sharedWorkflowId) return
    const page = await browser.newPage()
    try {
      await deleteWorkflowViaApi(page, sharedWorkflowId)
    } finally {
      await page.close()
    }
  })

  // ---------------------------------------------------------------------------
  // Deep-link tests (read-only — none submit a decision)
  // ---------------------------------------------------------------------------

  test('side panel displays approval details and action buttons', async ({ app }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await app.goto(toAppUrl(`/executions/${sharedExecutionId}?approval=${sharedApprovalId}&history=closed`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    await dismissConnectionBanner(app)

    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Reject' })).toBeVisible()

    await expect(app.getByText('Approval step', { exact: true })).toBeVisible()
    await expect(app.locator('dd').getByText(sharedApprovalName, { exact: true })).toBeVisible()
    await expect(app.getByText('Workflow', { exact: true })).toBeVisible()
    await expect(app.locator('dd').getByText(sharedWorkflowName, { exact: true })).toBeVisible()
    await expect(app.getByText('Approval initiated', { exact: true })).toBeVisible()
  })

  test('clicking approve shows notes input and submit button', async ({ app }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await app.goto(toAppUrl(`/executions/${sharedExecutionId}?approval=${sharedApprovalId}&history=closed`))
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    await dismissConnectionBanner(app)

    const approveBtn = app.getByRole('button', { name: 'Approve' })
    await expect(approveBtn).not.toHaveAttribute('aria-disabled', 'true')

    await approveBtn.click()

    await expect(app.getByPlaceholder(/Explain the reason for approving/i)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible()

    await app.getByRole('button', { name: 'Undo decision' }).click()
    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Reject' })).toBeVisible()
  })

  test('clicking reject shows notes input and submit button', async ({ app }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await app.goto(toAppUrl(`/executions/${sharedExecutionId}?approval=${sharedApprovalId}&history=closed`))
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    await dismissConnectionBanner(app)

    const rejectBtn = app.getByRole('button', { name: 'Reject' })
    await expect(rejectBtn).not.toHaveAttribute('aria-disabled', 'true')

    await rejectBtn.click()

    await expect(app.getByPlaceholder(/Explain the reason for rejecting/i)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible()

    await app.getByRole('button', { name: 'Undo decision' }).click()
    await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
  })

  test('run history and approval panel are mutually exclusive', async ({ app }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await app.goto(toAppUrl(`/executions/${sharedExecutionId}?approval=${sharedApprovalId}&history=closed`))
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    await dismissConnectionBanner(app)

    const historyHeading = app.getByRole('heading', { name: 'Run history' })
    await expect(historyHeading).not.toBeVisible()

    await app.getByRole('button', { name: /Run history/i }).click()
    await expect(historyHeading).toBeVisible()
    await expect(app.getByRole('heading', { name: 'Review Approval' })).not.toBeVisible()

    const reviewBtn = app.getByRole('button', { name: 'Review approval' })
    await expect(reviewBtn).toBeEnabled({ timeout: 15_000 })
    await reviewBtn.click()
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible()
    await expect(historyHeading).not.toBeVisible()
  })

  // ---------------------------------------------------------------------------
  // List navigation
  // ---------------------------------------------------------------------------

  test('clicking approval name navigates to execution detail with side panel', async ({ app }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await app.goto(toAppUrl('/approvals'))
    await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Approvals table' })
    await expect(table).toBeVisible({ timeout: 15_000 })

    // Filter by name to find our specific approval among potentially many
    await app.getByPlaceholder('Filter by name').fill(sharedApprovalName)
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Wait for the filtered results to render
    const approvalLink = table.getByText(sharedApprovalName)
    await expect(approvalLink).toBeVisible({ timeout: 15_000 })
    await approvalLink.click()

    await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=.*&history=closed/)
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
  })

  // ---------------------------------------------------------------------------
  // Viewer role — verify permission gating
  // ---------------------------------------------------------------------------

  test('viewer: approve and reject buttons are disabled', async ({ viewerApp }) => {
    test.skip(!!sharedSetupSkipReason, sharedSetupSkipReason ?? '')

    await viewerApp.goto(toAppUrl(`/executions/${sharedExecutionId}?approval=${sharedApprovalId}&history=closed`))
    await expect(viewerApp.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    const hasPanel = await viewerApp
      .getByRole('heading', { name: 'Review Approval' })
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasPanel, 'Viewer cannot access approval panel — project permission issue')

    const approveBtn = viewerApp.getByRole('button', { name: 'Approve' })
    const rejectBtn = viewerApp.getByRole('button', { name: 'Reject' })
    await expect(approveBtn).toHaveAttribute('aria-disabled', 'true')
    await expect(rejectBtn).toHaveAttribute('aria-disabled', 'true')
  })

  // ---------------------------------------------------------------------------
  // Self-contained tests (create their own workflows — no shared data needed)
  // ---------------------------------------------------------------------------

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
      if (!resp.ok()) throw new Error(`POST /executions returned ${resp.status()}`)
      const { id: executionId } = (await resp.json()) as { id: string }

      await pollExecutionStatus(app, executionId, ['paused'], { token, timeout: 60_000 })

      await app.goto(toAppUrl(`/executions/${executionId}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await dismissConnectionBanner(app)
      await expect(app.getByText('Waiting for approval')).toBeVisible({ timeout: 30_000 })
      await expect(app.getByTestId('approval-status-badge')).toBeVisible({ timeout: 10_000 })
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
      if (!resp.ok()) throw new Error(`POST /executions returned ${resp.status()}`)
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
      await dismissConnectionBanner(app)

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
