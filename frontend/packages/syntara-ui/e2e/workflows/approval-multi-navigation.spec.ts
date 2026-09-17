import { test, expect, toAppUrl } from '../fixtures'
import { dismissConnectionBanner, waitForApprovalPanel } from '../helpers/approvals'
import { clickWhenEnabled } from '../helpers/patternfly'
import { buildUniqueName } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
  publishWorkflowViaApi,
} from '../utils/api'

/** Per-step budget inside the navigation retry, so a stomped attempt fails fast. */
const NAV_STEP_TIMEOUT = 5_000

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
    const prevButton = app.getByRole('button', { name: 'Previous approval' })
    const nextButton = app.getByRole('button', { name: 'Next approval' })

    /**
     * `useAutoApprovalDetection` fires once per node entering WAITING, so two
     * parallel approval nodes fire it twice. Each landing reaches
     * `handleDetected` in `useExecutionApprovalPanel`, which hard-overwrites the
     * selected index via `setApprovalsAndIndex` — it has no notion that the user
     * (here, the test) navigated in between. A detection arriving between the
     * Next click and the "2 of 2" assertion snaps the panel back to "1 of 2",
     * and the Previous button the test then reaches for is `isAriaDisabled`.
     * Playwright honours `aria-disabled` in its actionability wait, and with no
     * `actionTimeout` that click waits out the whole (slow) test budget — the
     * observed 360s.
     *
     * Re-running the whole sequence from a fresh deep-link is the honest fix:
     * the detections are bounded at one per node and serialised by the hook, so
     * a retry lands after they are done. `clickWhenEnabled` keeps a stomped
     * attempt from hanging instead of retrying.
     *
     * `toBeDisabled` / `toBeEnabled` below are real assertions, not no-ops —
     * Playwright resolves both through `aria-disabled`.
     */
    await expect(async () => {
      await app.goto(deepLink1)
      await waitForApprovalPanel(app)
      await dismissConnectionBanner(app)
      await expect(panelHeading.getByText('1 of 2')).toBeVisible({ timeout: NAV_STEP_TIMEOUT })
      await expect(prevButton).toBeDisabled({ timeout: NAV_STEP_TIMEOUT })

      // Navigate forward to second approval
      await clickWhenEnabled(nextButton, { timeout: NAV_STEP_TIMEOUT })
      await expect(panelHeading.getByText('2 of 2')).toBeVisible({ timeout: NAV_STEP_TIMEOUT })
      await expect(nextButton).toBeDisabled({ timeout: NAV_STEP_TIMEOUT })

      // Navigate backward to first approval
      await clickWhenEnabled(prevButton, { timeout: NAV_STEP_TIMEOUT })
      await expect(panelHeading.getByText('1 of 2')).toBeVisible({ timeout: NAV_STEP_TIMEOUT })
      await expect(nextButton).toBeEnabled({ timeout: NAV_STEP_TIMEOUT })
    }).toPass({ timeout: 60_000, intervals: [5_000] })

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
})
