/**
 * Regression tests for the `triggerVerifyWorkflow` helper itself.
 *
 * The builder refetches the workflow, its versions and its executions right after
 * a save, and that re-render can tear down an already-open kebab menu. The helper
 * is supposed to survive that by re-opening the menu and clicking again, so these
 * tests drive it against a synthetic page that reproduces the tear-down on demand
 * rather than waiting for the race to show up in CI.
 */
import { test, expect, toAppUrl } from './fixtures'
import { triggerVerifyWorkflow, VALIDATE_ROUTE } from './helpers/workflow-verify'

const FIXTURE_PATH = '/e2e-fixtures/verify-kebab'

/**
 * Minimal stand-in for the builder toolbar kebab.
 *
 * The first time the menu opens, the item removes itself as soon as the mouse
 * reaches it — Playwright has already judged it visible, enabled and stable by
 * then, so the click is swallowed and reported as "element was detached from the
 * DOM, retrying", exactly like the post-save re-render does in CI. Every later
 * open behaves normally and posts to the validate endpoint.
 */
const FIXTURE_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" aria-label="Workflow actions" onclick="openMenu()">…</button>
    <div id="menu-slot"></div>
    <script>
      let detachArmed = true
      function openMenu() {
        const slot = document.getElementById('menu-slot')
        slot.innerHTML =
          '<div role="menu">' +
          '<button type="button" role="menuitem" onclick="verify()">Verify workflow</button>' +
          '</div>'
        if (detachArmed) {
          slot.querySelector('[role="menuitem"]').addEventListener('mousemove', () => {
            detachArmed = false
            slot.innerHTML = ''
          })
        }
      }
      function verify() {
        document.getElementById('menu-slot').innerHTML = ''
        void fetch('/api/v1/workflows/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workflow_definition: {} }),
        })
      }
    </script>
  </body>
</html>`

test.describe('triggerVerifyWorkflow helper', () => {
  // No login needed: the helper is driven against a synthetic page, not the app.
  test('re-opens the kebab and posts to validate after the menu detaches mid-click', async ({ page }) => {
    const validateRequests: string[] = []

    await page.route(`**${FIXTURE_PATH}`, (route) =>
      route.fulfill({ status: 200, contentType: 'text/html', body: FIXTURE_HTML })
    )
    await page.route(VALIDATE_ROUTE, (route) => {
      validateRequests.push(route.request().url())
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ valid: true, errors: [] }),
      })
    })

    await page.goto(toAppUrl(FIXTURE_PATH))
    await expect(page.getByRole('button', { name: 'Workflow actions' })).toBeVisible()

    // The first open is swallowed by the detach, so this only resolves if the helper
    // gives up on that click in time to re-open the menu and click again.
    await triggerVerifyWorkflow(page)

    expect(validateRequests).toHaveLength(1)
  })
})
