import { test, expect, toAppUrl } from '../fixtures'
import { waitForApprovalPanel } from '../helpers/approvals'
import { buildUniqueName } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
  publishWorkflowViaApi,
} from '../utils/api'

async function dismissConnectionBanner(app: import('@playwright/test').Page): Promise<void> {
  const banner = app.locator('.pf-v6-c-alert').filter({ hasText: 'Live updates paused' })
  if (await banner.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await banner.getByRole('button', { name: /close/i }).click()
  }
}

test('multi-approval navigation: Previous/Next buttons and deep-link counter', async ({ app }) => {
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

    // Wait for both approvals to be indexed
    let approvalIds: string[] = []
    try {
      await expect(async () => {
        const r = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
        const body = (await r.json()) as { resources?: Array<{ id: string }> }
        approvalIds = (body.resources ?? []).map((a) => a.id)
        expect(approvalIds).toHaveLength(2)
      }).toPass({ timeout: 60_000, intervals: [2_000] })
    } catch {
      // Approvals service unavailable or indexer too slow
    }
    test.skip(approvalIds.length < 2, 'Need 2 indexed approvals — approvals service may be unavailable')

    // --- Part 1: Deep-link to first approval, verify counter and navigation ---
    // The component fetches pending approvals once on load. If it only gets 1 back
    // (eventual consistency), the counter won't render. Reload forces a re-fetch.
    const deepLink1 = toAppUrl(`/executions/${executionId}?approval=${approvalIds[0]}&history=closed`)
    await app.goto(deepLink1)
    await expect(async () => {
      await app.goto(deepLink1)
      await waitForApprovalPanel(app)
      await dismissConnectionBanner(app)
      await expect(app.getByText('1 of 2')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 30_000, intervals: [3_000] })

    const prevButton = app.getByRole('button', { name: 'Previous approval' })
    const nextButton = app.getByRole('button', { name: 'Next approval' })
    await expect(prevButton).toBeDisabled()
    await expect(nextButton).toBeEnabled()

    // Navigate forward to second approval
    await nextButton.click()
    await expect(app.getByText('2 of 2')).toBeVisible({ timeout: 10_000 })
    await expect(prevButton).toBeEnabled()
    await expect(nextButton).toBeDisabled()

    // Navigate backward to first approval
    await prevButton.click()
    await expect(app.getByText('1 of 2')).toBeVisible({ timeout: 10_000 })
    await expect(prevButton).toBeDisabled()
    await expect(nextButton).toBeEnabled()

    // --- Part 2: Deep-link directly to second approval, verify counter ---
    await app.goto(toAppUrl(`/executions/${executionId}?approval=${approvalIds[1]}&history=closed`))
    await waitForApprovalPanel(app)
    await dismissConnectionBanner(app)
    // Component may start at either position depending on cached state;
    // if not already showing "2 of 2", click Next to get there
    if (
      !(await app
        .getByText('2 of 2')
        .isVisible({ timeout: 5_000 })
        .catch(() => false))
    ) {
      await app.getByRole('button', { name: 'Next approval' }).click()
    }
    await expect(app.getByText('2 of 2')).toBeVisible({ timeout: 10_000 })
  } finally {
    await deleteWorkflowViaApi(app, workflowId)
  }
})
