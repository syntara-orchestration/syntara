import type { Page } from '@playwright/test'

import { expect, toAppUrl } from '../fixtures'
import { pollApprovalVisible } from '../utils/api'

/**
 * Dismisses the "Live updates paused" connection banner if visible.
 * Uses role-based locator to stay off PatternFly class names.
 */
export async function dismissConnectionBanner(app: Page): Promise<void> {
  const banner = app.getByRole('alert').filter({ hasText: 'Live updates paused' })
  if (await banner.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await banner.getByRole('button', { name: /close/i }).click()
  }
}

/**
 * Waits for the approval review panel to be visible.
 * Verifies both URL navigation to execution detail with approval query param
 * and the "Review Approval" heading visibility.
 *
 * @param app - Playwright Page object
 * @param timeout - Optional timeout in milliseconds (default: 15000)
 */
export async function waitForApprovalPanel(app: Page, timeout = 15_000): Promise<void> {
  await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=/)
  await expect(app.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout })
}

/**
 * Navigate to the approvals page, filter by approval name, and open the approval panel.
 * This helper reduces duplication across tests that need to navigate to and open a specific approval.
 *
 * @param app - Playwright Page object
 * @param approvalName - Unique approval name to filter by (from buildUniqueName())
 *
 * @example
 * const approval = await createPendingApproval(app)
 * await navigateToApprovalAndOpen(app, approval.approvalName)
 * // Now in execution detail with approval panel open
 */
export async function navigateToApprovalAndOpen(app: Page, approvalName: string): Promise<void> {
  // Guard against the race between execution reaching "paused" and the approval record
  // becoming queryable in the listing API (the two are slightly asynchronous on the backend).
  await pollApprovalVisible(app, approvalName)

  await app.goto(toAppUrl('/approvals'))
  await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

  const approvalsTable = app.getByRole('grid', { name: 'Approvals table' })
  await expect(approvalsTable).toBeVisible({ timeout: 15_000 })

  await app.getByPlaceholder('Filter by name').fill(approvalName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const approvalBtn = approvalsTable.getByRole('button', { name: approvalName })
  await expect(approvalBtn).toBeVisible({ timeout: 15_000 })
  await approvalBtn.click()

  await waitForApprovalPanel(app)
}
