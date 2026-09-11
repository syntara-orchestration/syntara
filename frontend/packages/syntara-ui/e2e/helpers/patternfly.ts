import type { Page } from '../fixtures'

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
