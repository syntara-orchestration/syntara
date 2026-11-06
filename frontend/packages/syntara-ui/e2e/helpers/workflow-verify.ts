/**
 * Helpers for the builder's "Verify workflow" action.
 */
import { expect, type Page } from '../fixtures'

/** Glob for the workflow validation endpoint that "Verify workflow" posts to. */
export const VALIDATE_ROUTE = '**/api/v1/workflows/validate'

/** Per-attempt budget for landing each of the two clicks. */
const VERIFY_CLICK_TIMEOUT = 5_000
/** Per-attempt budget for the validate response to come back. */
const VERIFY_REQUEST_TIMEOUT = 10_000
/** Total budget for landing the menu click and getting a response. */
const VERIFY_RETRY_TIMEOUT = 30_000

/**
 * Trigger "Verify workflow" from the builder kebab and return once the validate
 * request has come back.
 *
 * Two separate races make a bare open-kebab-then-click flaky:
 *   1. The menu can close or re-render between the two clicks, so the click lands
 *      on a detaching item and no request is ever sent. The builder refetches the
 *      workflow, its versions and its executions right after a save, and that
 *      re-render tears the open menu down.
 *   2. On a loaded cluster the request itself can outlast a fixed banner wait.
 *
 * Gating on the response covers both: a swallowed click produces no response and
 * is retried, while a slow one is simply waited out.
 *
 * Both clicks get an explicit timeout and have their failure swallowed, because
 * Playwright retries a click on its own when the element detaches mid-action. An
 * unbounded click therefore stays inside a single `toPass` attempt for the whole
 * retry budget — the menu it waits on is already closed and never comes back, so
 * the only way out is to fall through to the response check and let `toPass`
 * re-open the kebab from scratch.
 *
 * Note that `handleVerify` does not always POST: it returns early when the builder
 * store has no current workflow, and again when `buildWorkflowDefinition` throws
 * (that path renders the "Verification failed" banner without a request). Neither
 * is reachable from the saved workflow every caller starts from.
 */
export async function triggerVerifyWorkflow(page: Page) {
  await expect(async () => {
    const kebab = page.getByRole('button', { name: 'Workflow actions' })
    const verifyItem = page.getByRole('menuitem', { name: /verify workflow/i })

    // Attach the catch up front so a throwing click cannot leave this rejecting unhandled
    const response = page
      .waitForResponse(VALIDATE_ROUTE, { timeout: VERIFY_REQUEST_TIMEOUT })
      .then(() => true)
      .catch(() => false)

    // Only click the kebab when the menu is closed — clicking it while open toggles it shut
    if (!(await verifyItem.isVisible().catch(() => false))) {
      await kebab.click({ timeout: VERIFY_CLICK_TIMEOUT }).catch(() => {})
    }
    await verifyItem.click({ timeout: VERIFY_CLICK_TIMEOUT }).catch(() => {})

    if (!(await response)) {
      throw new Error('Verify workflow did not produce a /workflows/validate response')
    }
  }).toPass({ timeout: VERIFY_RETRY_TIMEOUT, intervals: [1_000, 2_000, 3_000] })
}
