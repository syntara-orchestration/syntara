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
 */
import { test, expect, toAppUrl } from '../fixtures'
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
  test.skip(!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'], 'Temporal worker unavailable (globalSetup probe)')

  let workflowId: string
  let executionId: string
  let approvalId: string
  let approvalName: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      approvalName = buildUniqueName('side-panel-gate')
      const workflowName = buildUniqueName('e2e-side-panel')

      const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
      const nodes = [
        { id: 'approval_1', type: 'approval', name: approvalName, parameters: {} },
        { id: 'post_1', type: 'script', name: 'Post Approval', parameters: { language: 'python', code: 'pass' } },
      ]
      const edges = [
        { from: 'trigger_1', to: 'approval_1' },
        { from: 'approval_1', to: 'post_1', from_port: 'approved' },
      ]

      const result = await createWorkflowViaApi(page, workflowName, triggers, nodes, edges)
      workflowId = result.id
      await publishWorkflowViaApi(page, workflowId, result.versionNumber)

      const token = await getAuthToken(page)
      if (!token) throw new Error('Could not obtain auth token')

      const resp = await apiRequest(page, 'post', '/executions', {
        token,
        data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
      })
      if (!resp.ok()) throw new Error(`POST /executions returned ${resp.status()}`)
      const body = (await resp.json()) as { id: string }
      executionId = body.id

      await pollExecutionStatus(page, executionId, ['paused'], { token, timeout: 60_000 })

      await expect(async () => {
        const r = await apiRequest(page, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
        const data = (await r.json()) as { resources?: Array<{ id: string }> }
        approvalId = data.resources?.[0]?.id ?? ''
        expect(approvalId).toBeTruthy()
      }).toPass({ timeout: 30_000, intervals: [2_000] })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    if (!workflowId) return
    const page = await browser.newPage()
    try {
      await deleteWorkflowViaApi(page, workflowId)
    } finally {
      await page.close()
    }
  })

  test.describe('list navigation', () => {
    test('clicking approval name navigates to execution detail with side panel', async ({ app }) => {
      await app.goto(toAppUrl('/approvals'))
      await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Approvals table' })
      await table.waitFor({ state: 'visible', timeout: 15_000 })

      await app.getByPlaceholder('Filter by name').fill(approvalName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const approvalLink = table.getByRole('link', { name: approvalName })
      await expect(approvalLink).toBeVisible({ timeout: 15_000 })

      await approvalLink.click()

      await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=.*&history=closed/)
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    })
  })

  test.describe('deep-link', () => {
    test.beforeEach(async ({ app }) => {
      await app.goto(toAppUrl(`/executions/${executionId}?approval=${approvalId}&history=closed`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })
    })

    test('side panel displays approval details and action buttons', async ({ app }) => {
      await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Reject' })).toBeVisible()

      await expect(app.getByText('Approval step', { exact: true })).toBeVisible()
      await expect(app.locator('dd').getByText(approvalName, { exact: true })).toBeVisible()
      await expect(app.getByText('Workflow', { exact: true })).toBeVisible()
      await expect(app.getByText('Approval initiated', { exact: true })).toBeVisible()
    })

    test('clicking approve shows notes input and submit button', async ({ app }) => {
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
      const rejectBtn = app.getByRole('button', { name: 'Reject' })
      await expect(rejectBtn).not.toHaveAttribute('aria-disabled', 'true')

      await rejectBtn.click()

      await expect(app.getByPlaceholder(/Explain the reason for rejecting/i)).toBeVisible()
      await expect(app.getByRole('button', { name: 'Submit decision' })).toBeVisible()

      await app.getByRole('button', { name: 'Undo decision' }).click()
      await expect(app.getByRole('button', { name: 'Approve' })).toBeVisible()
    })

    test('run history and approval panel are mutually exclusive', async ({ app }) => {
      const historyHeading = app.getByRole('heading', { name: 'Run history' })
      await expect(historyHeading).not.toBeVisible()

      await app.getByRole('button', { name: /Run history/i }).click()
      await expect(historyHeading).toBeVisible()
      await expect(app.getByRole('heading', { name: 'Review Approval' })).not.toBeVisible()

      const reviewBtn = app.getByRole('button', { name: 'Review approval' })
      await reviewBtn.click()
      await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible()
      await expect(historyHeading).not.toBeVisible()
    })
  })

  test.describe('deep-link (viewer)', () => {
    test('viewer: approve and reject buttons are disabled', async ({ viewerApp }) => {
      await viewerApp.goto(toAppUrl(`/executions/${executionId}?approval=${approvalId}&history=closed`))
      await expect(viewerApp.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
      await expect(viewerApp.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })

      const approveBtn = viewerApp.getByRole('button', { name: 'Approve' })
      const rejectBtn = viewerApp.getByRole('button', { name: 'Reject' })
      // aria-disabled is set after the permissions API resolves — give it extra time
      await expect(approveBtn).toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })
      await expect(rejectBtn).toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })
    })
  })

  test.describe('self-contained', () => {
    test('UI-28: execution shows Paused status and Waiting for approval indicator', async ({ app }) => {
      test.slow()
      const localApprovalName = buildUniqueName('review-gate')
      const localWorkflowName = buildUniqueName('e2e-approval-panel')

      const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
      const nodes = [
        { id: 'approval_1', type: 'approval', name: localApprovalName, parameters: {} },
        { id: 'post_1', type: 'script', name: 'Post Approval', parameters: { language: 'python', code: 'pass' } },
      ]
      const edges = [
        { from: 'trigger_1', to: 'approval_1' },
        { from: 'approval_1', to: 'post_1', from_port: 'approved' },
      ]

      const { id: localWorkflowId, versionNumber } = await createWorkflowViaApi(
        app,
        localWorkflowName,
        triggers,
        nodes,
        edges
      )

      try {
        await publishWorkflowViaApi(app, localWorkflowId, versionNumber)

        const token = await getAuthToken(app)
        if (!token) throw new Error('Could not obtain auth token')

        const resp = await apiRequest(app, 'post', '/executions', {
          token,
          data: { workflow_id: localWorkflowId, trigger_node_id: 'trigger_1' },
        })
        expect(resp.ok(), `POST /executions returned ${resp.status()}`).toBeTruthy()
        const { id: localExecutionId } = (await resp.json()) as { id: string }

        await pollExecutionStatus(app, localExecutionId, ['paused'], { token, timeout: 60_000 })

        await app.goto(toAppUrl(`/executions/${localExecutionId}`))
        await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
        await expect(app.getByText('Waiting for approval')).toBeVisible({ timeout: 30_000 })
        await expect(app.getByRole('button', { name: 'Review approval' })).toBeVisible({ timeout: 30_000 })
      } finally {
        await deleteWorkflowViaApi(app, localWorkflowId)
      }
    })

    test('UI-30: rejecting an approval terminates workflow execution', async ({ app }) => {
      test.slow()
      const localApprovalName = buildUniqueName('rejection-gate')
      const localWorkflowName = buildUniqueName('e2e-reject')

      const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
      const nodes = [
        { id: 'approval_1', type: 'approval', name: localApprovalName, parameters: {} },
        { id: 'post_1', type: 'script', name: 'Post Approval', parameters: { language: 'python', code: 'pass' } },
      ]
      const edges = [
        { from: 'trigger_1', to: 'approval_1' },
        { from: 'approval_1', to: 'post_1', from_port: 'approved' },
      ]

      const { id: localWorkflowId, versionNumber } = await createWorkflowViaApi(
        app,
        localWorkflowName,
        triggers,
        nodes,
        edges
      )

      try {
        await publishWorkflowViaApi(app, localWorkflowId, versionNumber)

        const token = await getAuthToken(app)
        if (!token) throw new Error('Could not obtain auth token')

        const resp = await apiRequest(app, 'post', '/executions', {
          token,
          data: { workflow_id: localWorkflowId, trigger_node_id: 'trigger_1' },
        })
        expect(resp.ok(), `POST /executions returned ${resp.status()}`).toBeTruthy()
        const { id: localExecutionId } = (await resp.json()) as { id: string }

        await pollExecutionStatus(app, localExecutionId, ['paused'], { token, timeout: 60_000 })

        let localApprovalId: string | undefined
        await expect(async () => {
          const r = await apiRequest(app, 'get', `/approvals?execution_id=${localExecutionId}&status=pending`, {
            token,
          })
          const body = (await r.json()) as { resources?: Array<{ id: string }> }
          localApprovalId = body.resources?.[0]?.id
          expect(localApprovalId).toBeTruthy()
        }).toPass({ timeout: 30_000, intervals: [2_000] })

        await app.goto(toAppUrl(`/executions/${localExecutionId}?approval=${localApprovalId}&history=closed`))
        await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
        await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 30_000 })

        await app.getByRole('button', { name: 'Reject', exact: true }).click()
        await app.getByPlaceholder(/Explain the reason for rejecting/i).fill('Rejected in E2E test')
        await app.getByRole('button', { name: 'Submit decision' }).click()

        await expect(app.getByText('Rejection submitted')).toBeVisible({ timeout: 15_000 })

        await pollExecutionStatus(
          app,
          localExecutionId,
          ['completed', 'completed_with_errors', 'failed', 'cancelled'],
          {
            token,
            timeout: 60_000,
          }
        )
        await app.reload()
        await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
        await expect(app.getByTestId('execution-status-badge').getByText(/Completed|Failed|Rejected/i)).toBeVisible({
          timeout: 30_000,
        })
      } finally {
        await deleteWorkflowViaApi(app, localWorkflowId)
      }
    })
  })
})
