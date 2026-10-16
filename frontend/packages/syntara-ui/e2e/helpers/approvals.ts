import type { Locator } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import { pollApprovalVisible } from '../utils/api'

import { APP_TITLE } from './appTitle'

/** Canonical approvals list URL (Tasks → Approvals tab). Legacy `/approvals` redirects here. */
export const APPROVALS_LIST_PATH = '/tasks/approvals'

/** Wait for the Tasks page with the Approvals tab list loaded. */
export async function gotoApprovalsList(app: Page): Promise<void> {
  await app.goto(toAppUrl(APPROVALS_LIST_PATH))
  await expect(app.getByRole('heading', { level: 1, name: 'Tasks' })).toBeVisible({ timeout: 15_000 })
  await expect(app.getByRole('tab', { name: 'Approvals' })).toBeVisible()
  await expect(app.getByRole('tabpanel', { name: 'Approvals' })).toBeVisible({ timeout: 15_000 })
}

/** Document title for the approvals list (Tasks shell, Approvals tab). */
export async function expectApprovalsListPageTitle(app: Page): Promise<void> {
  await expect(app).toHaveTitle(`Tasks | ${APP_TITLE}`)
}

/**
 * Dismisses the "Live updates paused" connection banner if visible.
 * Uses role-based locator to stay off PatternFly class names.
 */
export async function dismissConnectionBanner(app: Page): Promise<void> {
  const banner = app.getByRole('alert').filter({ hasText: 'Live updates paused' })
  if (await banner.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await banner.getByRole('button', { name: /close/i }).click()
    await banner.waitFor({ state: 'hidden', timeout: 5_000 })
  }
}

/** Bulk Approve/Reject controls live in the list toolbar (not the Compass page header). */
export function getApprovalsBulkToolbar(app: Page, selectedCount: number): Locator {
  return app.getByRole('toolbar', { name: `${selectedCount} selected` })
}

/**
 * Applies a name filter on the approvals list and waits until the UI reflects the filter.
 * Waits for the filter chip and optional row content so batch tests do not race the table refresh.
 */
export async function applyApprovalNameFilter(
  app: Page,
  table: Locator,
  nameFilter: string,
  options?: { waitForRowText?: string }
): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(nameFilter)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })).toBeVisible({
    timeout: 15_000,
  })

  if (options?.waitForRowText) {
    await expect(table.getByRole('row').filter({ hasText: options.waitForRowText })).toBeVisible({
      timeout: 15_000,
    })
  }
}

/**
 * Waits for the approval review panel to be visible.
 * Verifies both URL navigation to execution detail with approval query param
 * and the "Review approval" heading visibility.
 *
 * @param app - Playwright Page object
 * @param timeout - Optional timeout in milliseconds (default: 15000)
 */
export async function waitForApprovalPanel(app: Page, timeout = 15_000): Promise<void> {
  await expect(app).toHaveURL(/\/executions\/[^?]+\?approval=/)
  await expect(app.getByRole('heading', { name: 'Review approval' })).toBeVisible({ timeout })
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

  await gotoApprovalsList(app)

  const approvalsTable = app.getByRole('grid', { name: 'Approvals table' })
  await expect(approvalsTable).toBeVisible({ timeout: 15_000 })

  await applyApprovalNameFilter(app, approvalsTable, approvalName, { waitForRowText: approvalName })

  const approvalLink = approvalsTable.getByRole('link', { name: approvalName })
  await expect(approvalLink).toBeVisible({ timeout: 15_000 })
  await approvalLink.click()

  await waitForApprovalPanel(app, 30_000)
}
