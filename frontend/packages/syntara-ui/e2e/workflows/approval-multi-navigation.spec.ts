import { test, expect, toAppUrl } from '../fixtures'
import { dismissConnectionBanner, waitForApprovalPanel } from '../helpers/approvals'
import { buildUniqueName } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
  publishWorkflowViaApi,
} from '../utils/api'

test(
  'multi-approval navigation: Previous/Next buttons and deep-link counter',
  { tag: ['@konflux-skip'] },
  async ({ app }) => {
    test.slow()

    const approvalNames = [buildUniqueName('nav-a'), buildUniqueName('nav-b')]
    const workflowName = buildUniqueName('multi-approval')
    const triggers = [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }]
    const nodes = approvalNames.flatMap((name, i) => [
      { id: `approval_${i + 1}`, type: 'approval', name, parameters: {} },
      { id: `post_${i + 1}`, type: 'script', name: `Post ${name}`, parameters: { language: 'python', code: 'pass' } },
    ])
    const edges = approvalNames.flatMap((_, i) => [
      { from: 'trigger_1', to: `approval_${i + 1}` },
      { from: `approval_${i + 1}`, to: `post_${i + 1}`, from_port: 'approved' },
    ])

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

      // Wait for both approvals to be indexed — skip only if the API is unreachable
      const probeResp = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
      test.skip(!probeResp.ok(), `Approvals API returned ${probeResp.status()} — service may be unavailable`)

      let approvalIds: string[] = []
      await expect(async () => {
        const r = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
        const body = (await r.json()) as { resources?: Array<{ id: string }> }
        approvalIds = (body.resources ?? []).map((a) => a.id)
        expect(approvalIds).toHaveLength(2)
      }).toPass({ timeout: 60_000, intervals: [2_000] })

      // --- Part 1: Deep-link to first approval, verify counter and navigation ---
      // The component fetches pending approvals once on load. If it only gets 1 back
      // (eventual consistency), the counter won't render. Reload forces a re-fetch.
      const panelHeading = app.getByRole('heading', { name: /Review approval/i })

      const deepLink1 = toAppUrl(`/executions/${executionId}?approval=${approvalIds[0]}&history=closed`)
      await app.goto(deepLink1)
      await expect(async () => {
        await app.goto(deepLink1)
        await waitForApprovalPanel(app)
        await dismissConnectionBanner(app)
        await expect(panelHeading.getByText('1 of 2')).toBeVisible({ timeout: 5_000 })
      }).toPass({ timeout: 60_000, intervals: [5_000] })

      const prevButton = app.getByRole('button', { name: 'Previous approval' })
      const nextButton = app.getByRole('button', { name: 'Next approval' })
      await expect(prevButton).toBeDisabled()
      await expect(nextButton).toBeEnabled()

      // Navigate forward to second approval
      await nextButton.click()
      await expect(panelHeading.getByText('2 of 2')).toBeVisible({ timeout: 10_000 })
      await expect(prevButton).toBeEnabled()
      await expect(nextButton).toBeDisabled()

      // Navigate backward to first approval
      await prevButton.click()
      await expect(panelHeading.getByText('1 of 2')).toBeVisible({ timeout: 10_000 })
      await expect(prevButton).toBeDisabled()
      await expect(nextButton).toBeEnabled()

      // --- Part 2: Deep-link directly to second approval, verify counter ---
      const deepLink2 = toAppUrl(`/executions/${executionId}?approval=${approvalIds[1]}&history=closed`)
      await expect(async () => {
        await app.goto(deepLink2)
        await waitForApprovalPanel(app)
        await dismissConnectionBanner(app)
        await expect(panelHeading.getByText('2 of 2')).toBeVisible({ timeout: 5_000 })
      }).toPass({ timeout: 60_000, intervals: [5_000] })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  }
)
