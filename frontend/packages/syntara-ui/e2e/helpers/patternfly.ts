import type { Locator } from '@playwright/test'

import { expect, type Page } from '../fixtures'

/**
 * PatternFly 6 widgets that do not expose a stable ARIA role.
 *
 * Toast Alert is `aria-live="polite"` only (no `role="alert"`), so
 * `getByRole('alert')` is a no-op. Pagination's "1–N of M" text lives in the
 * options menu, not inside the `<nav aria-label="Pagination">`.
 *
 * OUIA `data-ouia-component-type` is the same stable hook `waitForUIReady` uses.
 * `data-*` locators are allowed; `.pf-v6-c-*` class selectors are not.
 *
 * Popover has no OUIA attribute — assert on its body text (see FieldHelpPopover
 * tests) rather than `getByRole('dialog')`, which also matches open modals.
 */
export function pfWidget(page: Page, type: 'Alert' | 'Pagination') {
  return page.locator(`[data-ouia-component-type="PF6/${type}"]`)
}

/**
 * Compact list pagination (count text + per-page toggle + prev/next).
 * PatternFly may emit more than one `PF6/Pagination` node (top + bottom, or an
 * inner wrapper). Specs cannot use `.last()`; pick the footer here.
 */
export function paginationFooter(page: Page) {
  return pfWidget(page, 'Pagination').last()
}

/** Pagination pinned to the scrollable table that owns `gridName`. */
export function paginationFooterForTable(page: Page, gridName: string) {
  return page
    .getByTestId('scrollable-table-container-root')
    .filter({ has: page.getByRole('grid', { name: gridName }) })
    .locator('[data-ouia-component-type="PF6/Pagination"]')
}

/**
 * Active filter chips for one category (e.g. Name).
 * Scoped to FilterBar (`role="search"` / `aria-label="Filters"`). Use
 * `getByRole('list', { name })` — the category text is the accessible name,
 * not a descendant of the list, so `.filter({ hasText })` does not match.
 */
export function filterChipGroup(page: Page, categoryName: string) {
  return page.getByRole('search', { name: 'Filters' }).getByRole('list', { name: categoryName })
}

/** Budget for a PF button to become actionable, and for the click itself. */
const ARIA_DISABLED_CLICK_TIMEOUT = 10_000

/**
 * Click a PatternFly button that may be rendered with `isAriaDisabled`.
 *
 * PF uses `isAriaDisabled` rather than `disabled` so the button keeps focus and
 * can carry an explanatory tooltip, and Playwright resolves its "enabled"
 * actionability check through `aria-disabled`. With no `actionTimeout` in
 * `playwright.config.ts`, `click()` on such a button waits out the whole test
 * timeout and the run reports "Test timeout exceeded" with no failing assertion
 * to explain it. Two of these have already done exactly that: the approval
 * panel's Previous/Next at the ends of the list (`ApprovalNavigationHeader`),
 * and `ApprovalActionButtons`' Review approval while the panel is open.
 *
 * Bounding both the readiness wait and the click turns that into a fast failure
 * that names the button. Note this does NOT make an oscillating disabled state
 * safe — where the app can flip the button back to disabled under the test, the
 * caller still needs a `toPass` whose success condition is the end state rather
 * than the click.
 */
export async function clickWhenEnabled(
  target: Locator,
  { timeout = ARIA_DISABLED_CLICK_TIMEOUT }: { timeout?: number } = {}
): Promise<void> {
  await expect(target).toBeEnabled({ timeout })
  await target.click({ timeout })
}

/** Per-attempt budget for landing the kebab click. */
const KEBAB_CLICK_TIMEOUT = 5_000
/** Per-attempt budget for the menu to render once the kebab has been clicked. */
const KEBAB_MENU_TIMEOUT = 5_000
/** Total budget for getting the menu open. */
const KEBAB_RETRY_TIMEOUT = 30_000

/**
 * Open a table row's kebab menu, returning once `probeItem` is on the page.
 *
 * A row is re-rendered whenever the list query behind it resolves — a filter
 * being applied, a cursor page landing, a refetch after a mutation — and a click
 * that lands while React is replacing the row is simply lost. The menu never
 * opens, and the caller fails much later on a missing `menuitem` with nothing in
 * the trace to say why. `force: true` makes that strictly more likely, because it
 * skips the actionability wait that would otherwise have held the click until the
 * row was stable; every row kebab in the suite is clicked that way today.
 *
 * Re-opening on a miss is the same remedy `triggerVerifyWorkflow` uses for the
 * builder kebab. The toggle is only clicked while the menu is closed, since
 * clicking it again would toggle it shut — so a menu that is merely slow is
 * waited out rather than dismissed.
 */
export async function openRowKebab(row: Locator, probeItem: RegExp | string): Promise<void> {
  const page = row.page()
  const kebab = row.getByRole('button', { name: /Actions|Kebab toggle/i })
  const item = page.getByRole('menuitem', { name: probeItem })

  await expect(async () => {
    if (!(await item.isVisible().catch(() => false))) {
      await expect(row).toBeVisible({ timeout: KEBAB_CLICK_TIMEOUT })
      // Swallow the click failure: Playwright retries a click on its own when the
      // element detaches, so an unbounded one would sit inside a single attempt
      // for the whole retry budget instead of letting `toPass` start over.
      await kebab.click({ timeout: KEBAB_CLICK_TIMEOUT }).catch(() => {})
    }
    await expect(item).toBeVisible({ timeout: KEBAB_MENU_TIMEOUT })
  }).toPass({ timeout: KEBAB_RETRY_TIMEOUT, intervals: [500, 1_000, 2_000] })
}
