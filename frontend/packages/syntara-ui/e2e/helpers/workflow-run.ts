import { type Locator, type Page } from '@playwright/test'

import { expect } from '../fixtures'

/** Locator scoped to the Compass page-header region (h1, status badges, toolbar). */
export const pageHeader = (page: Page): Locator => page.locator('.pf-v6-c-compass__main-header')

/**
 * Click Run in the workflow builder toolbar and wait for navigation to the
 * execution detail page. Handles the "Save conflict" dialog that can appear
 * when the implicit save-before-run races with an explicit save.
 */
export async function runWorkflowFromBuilder(page: Page): Promise<void> {
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  await page.getByRole('button', { name: /Run now|Save and run/ }).click()

  const gotConflict = await page
    .getByText('newer version available')
    .waitFor({ state: 'visible', timeout: 3_000 })
    .then(() => true)
    .catch(() => false)

  if (gotConflict) {
    await page.getByRole('button', { name: 'Refresh to latest' }).click()
    await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Run', exact: true }).click()
    await page.getByRole('button', { name: /Run now|Save and run/ }).click()
  }

  await page.waitForURL(/\/executions\//, { timeout: 30_000 })
}

/**
 * Wait for a workflow execution to reach the approval-paused state on the
 * execution detail page.  Uses the "Pending approval" badge scoped to the
 * page header — the badge is driven by the `approval_pending` boolean
 * (set when any approval activity is in `waiting` status) and is more
 * reliable than the "Paused" status label which depends on a WebSocket
 * `/status` patch that can be delayed or stale.
 *
 * Scoped to the page header to avoid false-matching "Pending approval"
 * text elsewhere on the page (e.g. activity table, side panel).
 *
 * Splits the wait into two phases with a page refresh between them so that
 * a stale or late-connecting WebSocket doesn't cause a false negative —
 * the refresh forces a fresh API fetch.
 */
export async function waitForExecutionPaused(page: Page, timeout = 90_000): Promise<boolean> {
  const half = Math.floor(timeout / 2)
  const reloadHeadingBudget = 10_000
  const indicator = pageHeader(page).getByText('Pending approval')

  const reached = await indicator
    .waitFor({ state: 'visible', timeout: half })
    .then(() => true)
    .catch(() => false)

  if (reached) return true

  await page.reload()
  await page
    .getByRole('heading', { level: 1 })
    .waitFor({ state: 'visible', timeout: reloadHeadingBudget })
    .catch(() => {})

  return indicator
    .waitFor({ state: 'visible', timeout: Math.max(half - reloadHeadingBudget, 5_000) })
    .then(() => true)
    .catch(() => false)
}
