/**
 * Regression test for the `deleteWorkflow` cleanup helper itself.
 *
 * The helper prefers an API delete and only falls back to the UI when the name
 * lookup finds nothing — which is the ordinary case in a `finally` block, because
 * the workflow was renamed during the test or an earlier cleanup call already
 * removed it. When the project is then empty the Workflows page renders the
 * "No workflows yet" empty state, which has no filter toolbar, and the helper's
 * unbounded `fill('Filter by name')` used to wait out the entire test timeout —
 * failing a test whose assertions had all passed.
 *
 * This drives the helper against a synthetic empty-state page so the hang is
 * reproduced on demand rather than whenever CI happens to leave the list empty.
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, deleteWorkflow } from './helpers/workflows'

/**
 * The Workflows page as it renders with nothing to list: a heading, a call to
 * action, and deliberately no "Filter by name" input — that absence is the whole
 * hazard.
 */
const EMPTY_STATE_HTML = `<!doctype html>
<html lang="en">
  <body>
    <h1>Workflows</h1>
    <h2>No workflows yet</h2>
    <p>Create your first workflow to get started.</p>
    <button type="button">Create workflow</button>
  </body>
</html>`

test.describe('deleteWorkflow helper', () => {
  // No login needed: the helper is driven against a synthetic page, not the app.
  test('gives up instead of hanging when the workflow list is empty', async ({ page }) => {
    test.setTimeout(60_000)

    // A name nothing was ever seeded under, so the helper's API lookup returns
    // null and it takes the UI fallback — exactly the path CI took.
    const missingWorkflow = buildUniqueName('e2e-cleanup-missing')

    await page.route(toAppUrl('/workflows'), (route) =>
      route.fulfill({ status: 200, contentType: 'text/html', body: EMPTY_STATE_HTML })
    )

    const settled = await Promise.race([
      deleteWorkflow(page, missingWorkflow).then(() => 'returned' as const),
      page.waitForTimeout(20_000).then(() => 'still-waiting' as const),
    ])

    expect(settled, 'deleteWorkflow must give up on the missing filter toolbar, not consume the test timeout').toBe(
      'returned'
    )

    // And it must stay best-effort: giving up is not an error the caller sees.
    await expect(page.getByRole('heading', { name: 'No workflows yet' })).toBeVisible()
  })
})
