/**
 * Regression tests for the `clickWhenEnabled` helper itself.
 *
 * PatternFly renders a disabled button with `aria-disabled` rather than
 * `disabled`, and Playwright honours that in its actionability wait. With no
 * `actionTimeout` configured, a bare `click()` on one of those buttons waits out
 * the entire test budget and the run reports "Test timeout exceeded" with no
 * failing assertion — which is exactly how the approval specs burned 120s and
 * 360s in the merge queue. These drive the helper against a synthetic page so
 * both halves of that behaviour are pinned.
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import { clickWhenEnabled, openRowKebab } from './helpers/patternfly'

const BECOMES_ENABLED_FIXTURE = '/e2e-fixtures/pf-becomes-enabled'
const STAYS_DISABLED_FIXTURE = '/e2e-fixtures/pf-stays-disabled'

/**
 * A button that drops `aria-disabled` after 1.5s.
 *
 * The click handler is wired the way `ApprovalActionButtons` wires it — only
 * while enabled — so a helper that force-clicked through `aria-disabled` would
 * fire nothing and the counter would stay at 0.
 */
const BECOMES_ENABLED_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" id="act" aria-disabled="true">Review approval</button>
    <output id="count">0</output>
    <script>
      const button = document.getElementById('act')
      const bump = () => {
        const out = document.getElementById('count')
        out.textContent = String(Number(out.textContent) + 1)
      }
      button.addEventListener('click', () => {
        if (button.getAttribute('aria-disabled') !== 'true') bump()
      })
      setTimeout(() => button.removeAttribute('aria-disabled'), 1500)
    </script>
  </body>
</html>`

/** A button that is `aria-disabled` for the life of the page. */
const STAYS_DISABLED_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" aria-disabled="true">Next approval</button>
  </body>
</html>`

async function serveFixture(page: Page, path: string, html: string): Promise<void> {
  await page.route(`**${path}`, (route) => route.fulfill({ status: 200, contentType: 'text/html', body: html }))
  await page.goto(toAppUrl(path))
}

test.describe('clickWhenEnabled helper', () => {
  // No login needed: the helper is driven against a synthetic page, not the app.
  test('waits for the button to drop aria-disabled, then clicks it exactly once', async ({ page }) => {
    await serveFixture(page, BECOMES_ENABLED_FIXTURE, BECOMES_ENABLED_HTML)

    await clickWhenEnabled(page.getByRole('button', { name: 'Review approval' }))

    // Exactly 1 — 0 would mean the helper clicked through `aria-disabled` and the
    // app's handler ignored it, which is a silent no-op the caller cannot see.
    await expect(page.getByRole('status')).toHaveText('1')
  })

  test('gives up instead of hanging on a permanently aria-disabled button', async ({ page }) => {
    test.setTimeout(60_000)
    await serveFixture(page, STAYS_DISABLED_FIXTURE, STAYS_DISABLED_HTML)

    const settled = await Promise.race([
      clickWhenEnabled(page.getByRole('button', { name: 'Next approval' })).then(
        () => 'resolved' as const,
        () => 'rejected' as const
      ),
      page.waitForTimeout(20_000).then(() => 'still-waiting' as const),
    ])

    expect(settled, 'an aria-disabled button must fail fast, not consume the test timeout').toBe('rejected')
  })
})

const KEBAB_FIXTURE = '/e2e-fixtures/pf-row-kebab'
const KEBAB_OPEN_FIXTURE = '/e2e-fixtures/pf-row-kebab-open'

/**
 * A row kebab whose *first* click is swallowed.
 *
 * That is what a click landing on a row React is in the middle of replacing looks
 * like from the outside: the button is there, the click reports success, and no
 * menu ever appears. `openRowKebab` has to notice and open it again.
 */
const KEBAB_HTML = `<!doctype html>
<html lang="en">
  <body>
    <table>
      <tbody>
        <tr>
          <td>e2e-perm-idp</td>
          <td><button type="button" id="kebab" aria-label="Actions">Kebab</button></td>
        </tr>
      </tbody>
    </table>
    <div id="menu" hidden><button type="button" role="menuitem" aria-disabled="true">Edit provider</button></div>
    <output id="count">0</output>
    <script>
      let clicks = 0
      document.getElementById('kebab').addEventListener('click', () => {
        clicks += 1
        document.getElementById('count').textContent = String(clicks)
        if (clicks < 2) return
        const menu = document.getElementById('menu')
        menu.hidden = !menu.hidden
      })
    </script>
  </body>
</html>`

/** The same row, but with the menu already open — clicking again would close it. */
const KEBAB_OPEN_HTML = KEBAB_HTML.replace('<div id="menu" hidden>', '<div id="menu">')

test.describe('openRowKebab helper', () => {
  test('re-opens the kebab when the first click is swallowed', async ({ page }) => {
    await serveFixture(page, KEBAB_FIXTURE, KEBAB_HTML)

    await openRowKebab(page.getByRole('row').filter({ hasText: 'e2e-perm-idp' }), /Edit provider/i)

    await expect(page.getByRole('menuitem', { name: /Edit provider/i })).toBeVisible()
    // 2, not 1 — a single click is exactly what the IdP spec did, and it left the
    // menu closed. If this ever reads 1 the retry has stopped being load-bearing.
    await expect(page.getByRole('status')).toHaveText('2')
  })

  test('does not click a kebab whose menu is already open', async ({ page }) => {
    await serveFixture(page, KEBAB_OPEN_FIXTURE, KEBAB_OPEN_HTML)

    await openRowKebab(page.getByRole('row').filter({ hasText: 'e2e-perm-idp' }), /Edit provider/i)

    await expect(page.getByRole('menuitem', { name: /Edit provider/i })).toBeVisible()
    // A click here would toggle the menu shut — the exact regression the
    // `isVisible` guard in the helper exists to prevent.
    await expect(page.getByRole('status')).toHaveText('0')
  })
})
