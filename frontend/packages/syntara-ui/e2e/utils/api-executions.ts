/**
 * Execution & approval polling helpers for E2E tests.
 */
import { expect, type Page } from '../fixtures'

import { apiRequest, getAuthToken } from './api-core'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function pendingListIncludesName(body: unknown, name: string): boolean {
  if (!isRecord(body)) return false
  const resources = body['resources']
  if (!Array.isArray(resources)) return false
  return resources.some((row) => isRecord(row) && row['name'] === name)
}

/**
 * Poll an execution's status via the API until it matches one of the expected values.
 * Retries every 1s until timeout (default 90s). Used to wait for Temporal state
 * transitions (e.g. "running", "paused", terminal statuses) without relying on UI updates.
 */
export async function pollExecutionStatus(
  app: Page,
  executionId: string,
  expectedStatuses: string[],
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  await expect(async () => {
    const resp = await apiRequest(app, 'get', `/executions/${executionId}`, { token })
    const exec = (await resp.json()) as { status: string }
    expect(expectedStatuses).toContain(exec.status)
  }).toPass({ timeout: options?.timeout ?? 90_000, intervals: [1_000] })
}

/**
 * Poll the approvals API until an approval with the given name is visible in the listing.
 * Use this after `pollExecutionStatus` reaches "paused" to guard against the brief async
 * gap between the execution being paused and the approval record being queryable.
 */
export async function pollApprovalVisible(
  app: Page,
  approvalName: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  // The /approvals endpoint does not support name filtering — scan pending approvals by name.
  await expect(async () => {
    const resp = await apiRequest(app, 'get', '/approvals?status=pending&limit=100', { token })
    const body = (await resp.json()) as { resources?: Array<{ name: string }> }
    const found = body.resources?.some((r) => r.name === approvalName)
    expect(found).toBe(true)
  }).toPass({ timeout: options?.timeout ?? 30_000, intervals: [1_000] })
}

/**
 * Poll the form prompts API until a pending prompt with the given name is listed.
 * Use after `pollExecutionStatus` reaches "paused" on real backends when Temporal is available.
 */
export async function pollFormPromptVisible(
  app: Page,
  promptName: string,
  options?: { token?: string; timeout?: number; executionId?: string }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  const executionId = options?.executionId
  await expect(async () => {
    const path =
      executionId && executionId.length > 0
        ? `/form_prompts?execution_id=${executionId}&status=pending&limit=100`
        : '/form_prompts?status=pending&limit=100'
    const resp = await apiRequest(app, 'get', path, { token })
    expect(pendingListIncludesName(await resp.json(), promptName)).toBe(true)
  }).toPass({ timeout: options?.timeout ?? 45_000, intervals: [1_000] })
}

export const TERMINAL_EXECUTION_STATUSES = ['completed', 'failed', 'cancelled', 'completed_with_errors'] as const

/**
 * Poll until a PENDING approval exists for the execution (backend E2E gate).
 * Prefer this over waiting for execution status "paused" — the run can still be "running"
 * while Temporal reaches the approval node.
 */
export async function pollPendingApprovalForExecution(
  app: Page,
  executionId: string,
  options?: { token?: string; timeout?: number }
): Promise<string> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  let approvalId = ''
  await expect(async () => {
    const resp = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&status=pending`, { token })
    const body = (await resp.json()) as { resources?: Array<{ id: string }> }
    approvalId = body.resources?.[0]?.id ?? ''
    expect(approvalId).toBeTruthy()
  }).toPass({ timeout: options?.timeout ?? 90_000, intervals: [1_000, 2_000] })
  return approvalId
}

/**
 * Shape of entries in `GET /executions/{id}?include=activities` → `activities[]`.
 * This is the *stripped-down* `ActivityData` schema — only `activity_id` + `status`
 * (plus timing/output). It does NOT include `node_type`, `activity_name`, or
 * `temporal_activity_id` — those only exist on the richer `ActivityExecution` schema
 * returned by `GET /executions/{id}/activities` (the dedicated activities list endpoint).
 */
type ExecutionActivityRow = {
  activity_id?: string
  status?: string
}

/** Match the approval's activity row by id, tolerating loop-iteration suffixes (`{id}_iter_N`). */
function formatApprovalActivityHint(
  approvalNodeId: string | undefined,
  activities: ExecutionActivityRow[] | undefined
): string {
  if (!activities?.length) return 'activities=not_loaded_or_empty (check ?include=activities)'
  const match =
    approvalNodeId != null
      ? (activities.find((a) => a.activity_id === approvalNodeId) ??
        activities.find((a) => a.activity_id?.startsWith(`${approvalNodeId}_iter_`)) ??
        activities.find((a) => a.activity_id?.startsWith(`${approvalNodeId}#`)))
      : undefined
  if (!match) {
    const allIds = activities.map((a) => `${a.activity_id ?? '?'}:${a.status ?? '?'}`).join(', ')
    return `approval_activity_not_found (all activities: ${allIds})`
  }
  return `approval_activity(id=${match.activity_id ?? '?'}, status=${match.status ?? '?'})`
}

/** After reject, poll until execution is terminal; surfaces signal/Temporal context on timeout. */
export async function pollExecutionTerminalAfterReject(
  app: Page,
  executionId: string,
  approvalId: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  const timeout = options?.timeout ?? 120_000
  await pollApprovalStatusById(app, approvalId, 'rejected', { token, timeout: 30_000 })
  await expect(async () => {
    const [execResp, apprResp] = await Promise.all([
      apiRequest(app, 'get', `/executions/${executionId}?include=activities`, { token }),
      apiRequest(app, 'get', `/approvals/${approvalId}`, { token }),
    ])
    const exec = (await execResp.json()) as { status: string; activities?: ExecutionActivityRow[] }
    const appr = (await apprResp.json()) as {
      status?: string
      approval_node_id?: string
    }
    const terminals = [...TERMINAL_EXECUTION_STATUSES]
    const settled = terminals.includes(exec.status as (typeof terminals)[number])
    const activityHint = formatApprovalActivityHint(appr.approval_node_id, exec.activities)
    expect(
      settled,
      [
        'Expected terminal execution after reject (approval row is rejected but run did not finish).',
        `execution.status=${exec.status}, approval.status=${appr.status ?? 'unknown'}.`,
        `approval_node_id=${appr.approval_node_id ?? '?'}.`,
        activityHint + '.',
        'If the approval activity status above is still "waiting", Temporal never completed it',
        '(check API logs for "Async activity already completed or timed out (idempotent no-op)").',
        'If it already shows "completed", the activity finished but execution status sync is lagging/stuck',
        '— a different bug (see activity_execution_state._maybe_update_execution_paused_status).',
      ].join(' ')
    ).toBe(true)
  }).toPass({ timeout, intervals: [1_000, 2_000, 3_000] })
}

/** Poll GET /approvals/{id} until the record reaches the expected decision status. */
export async function pollApprovalStatusById(
  app: Page,
  approvalId: string,
  expectedStatus: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  const expected = expectedStatus.toLowerCase()
  await expect(async () => {
    const resp = await apiRequest(app, 'get', `/approvals/${approvalId}`, { token })
    const body = (await resp.json()) as { status?: string }
    expect(body.status?.toLowerCase()).toBe(expected)
  }).toPass({ timeout: options?.timeout ?? 30_000, intervals: [1_000] })
}

/** Poll until an approval for this execution reaches the expected decision status (e.g. rejected). */
export async function pollApprovalStatusForExecution(
  app: Page,
  executionId: string,
  expectedStatus: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  const expected = expectedStatus.toLowerCase()
  await expect(async () => {
    const resp = await apiRequest(app, 'get', `/approvals?execution_id=${executionId}&limit=20`, { token })
    const body = (await resp.json()) as { resources?: Array<{ status: string }> }
    const statuses = (body.resources ?? []).map((r) => r.status.toLowerCase())
    expect(statuses).toContain(expected)
  }).toPass({ timeout: options?.timeout ?? 30_000, intervals: [1_000] })
}

/** Request cancellation and wait until the execution reaches a terminal status. */
export async function cancelExecutionViaApi(
  app: Page,
  executionId: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  const resp = await apiRequest(app, 'post', `/executions/${executionId}/cancel`, { token })
  expect(resp.ok() || resp.status() === 202, `cancel execution ${executionId} failed: ${resp.status()}`).toBeTruthy()
  await pollExecutionStatus(app, executionId, [...TERMINAL_EXECUTION_STATUSES], {
    token,
    timeout: options?.timeout ?? 90_000,
  })
}
