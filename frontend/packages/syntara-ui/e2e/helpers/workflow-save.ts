/**
 * Helpers for persisting a workflow from the builder toolbar.
 */
import { type Response } from '@playwright/test'

import { expect, type Page } from '../fixtures'

/**
 * Budget for landing the Save click.
 *
 * `SaveWorkflowButton` renders `isAriaDisabled` whenever the workflow is clean,
 * the node editor is open, or a save is already in flight, and Playwright
 * resolves its "enabled" actionability check through `aria-disabled`. With no
 * `actionTimeout` in `playwright.config.ts`, a bare `click()` on that button
 * waits out the entire test timeout and the run reports "Test timeout exceeded"
 * with no failing assertion to explain it.
 */
const SAVE_CLICK_TIMEOUT = 10_000

/**
 * Budget for the create/update request to come back.
 *
 * Deliberately larger than the 15s URL guard it replaces: `wait-node.spec.ts`
 * failed honestly at 15s under three workers, which is the save genuinely being
 * slow rather than the gate being wrong.
 */
const SAVE_RESPONSE_TIMEOUT = 30_000

/**
 * Budget for the toolbar to leave its pending state after the response.
 *
 * This covers the part of the save that happens in the browser rather than on
 * the wire — marking the store clean, invalidating the workflow queries and,
 * on create, routing to `/workflow-builder/<id>`.
 */
const SAVE_SETTLE_TIMEOUT = 10_000

/**
 * The two requests a Save click can produce, and nothing else under /workflows.
 *
 * Create is `POST /api/v1/workflows` and update is
 * `PATCH /api/v1/workflows/{workflow_id}` (`BuilderContent.tsx:204` and `:207`).
 * A glob cannot express this: `**\/api/v1/workflows/*` also matches the
 * `POST /workflows/validate` that "Verify workflow" sends, every
 * `GET /workflows/{id}` the builder refetches and the version-publish POSTs.
 * Anchoring on method plus path shape is what keeps those out.
 */
export function isWorkflowSaveResponse(response: Response): boolean {
  const method = response.request().method()
  const { pathname } = new URL(response.url())
  if (method === 'POST') return /\/api\/v1\/workflows$/.test(pathname)
  if (method === 'PATCH') return /\/api\/v1\/workflows\/[^/]+$/.test(pathname)
  return false
}

/**
 * Click the builder's Save button and return once the server has the change.
 *
 * The URL is not a usable gate. On create the builder does navigate from
 * `/workflow-builder/new` to `/workflow-builder/<id>`, but the guard most
 * callers wrote — `/workflow-builder\/.+/` — matches the literal `new` segment,
 * so it passes the instant the click is dispatched and before any request goes
 * out. On an existing workflow there is no navigation at all, so *no* URL guard
 * can work: even the `(?!new)` form is a no-op there. Either way the caller then
 * runs `goto('/workflows')`, which aborts the in-flight write and the row the
 * test is about never appears.
 *
 * Gating on the response covers both shapes, and it is the only signal that
 * exists for the rename case.
 *
 * Ordering matters twice over. The enabled assertion comes first because it
 * cannot itself trigger the request, so nothing is left pending if it throws.
 * The response wait is armed before the click because a mock-API create comes
 * back in single-digit milliseconds — arming after `click()` resolves loses the
 * race outright — and its rejection is swallowed up front so a throwing click
 * cannot leave an unhandled rejection behind.
 */
export async function clickSaveAndWait(
  page: Page,
  { timeout = SAVE_RESPONSE_TIMEOUT }: { timeout?: number } = {}
): Promise<void> {
  const wasNew = /\/workflow-builder\/new(?:[?#]|$)/.test(page.url())
  const saveButton = page.getByRole('button', { name: 'Save', exact: true })

  await expect(saveButton).toBeEnabled({ timeout: SAVE_CLICK_TIMEOUT })

  const savePromise: Promise<Response | null> = page
    .waitForResponse(isWorkflowSaveResponse, { timeout })
    .catch(() => null)

  await saveButton.click({ timeout: SAVE_CLICK_TIMEOUT })

  const response = await savePromise
  if (!response) {
    throw new Error(`Save produced no POST /workflows or PATCH /workflows/{id} response within ${timeout}ms`)
  }
  if (!response.ok()) {
    const body = await response.text().catch(() => '(unreadable)')
    throw new Error(
      `Save failed: ${response.request().method()} ${new URL(response.url()).pathname} ` +
        `returned ${response.status()}: ${body}`
    )
  }

  // The label is `Saving...` while the mutation is pending, so an exact-name
  // `Save` locator only resolves again once the save's onSuccess has run.
  await expect(saveButton).toBeVisible({ timeout: SAVE_SETTLE_TIMEOUT })

  // Create is the only case where the URL is evidence of anything — and then it
  // is `(?!new)`, never `.+`.
  if (wasNew) {
    await expect(page).toHaveURL(/workflow-builder\/(?!new)/, { timeout: SAVE_SETTLE_TIMEOUT })
  }
}
