/**
 * Execution & approval polling helpers for E2E tests.
 */
import { expect, type Page } from '../fixtures'

import { apiRequest, getAuthToken } from './api-core'

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
