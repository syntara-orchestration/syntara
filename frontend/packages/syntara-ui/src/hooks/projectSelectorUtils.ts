/**
 * Presentation constants and user-visible copy for the masthead / shell project picker.
 * Keep logic comparisons out of `projectSelectorUx` — use internal keys in code instead.
 */

import type { CSSProperties, RefObject } from 'react'

/**
 * No `--pf-t--global--*` width token exists for "select menu max width".
 * PatternFly's scrollable menu content often uses ~`18.75rem`; we match that for width.
 * Using the same value for min and max keeps the toggle and dropdown at a stable width
 * regardless of selected project name length or filtered result set size.
 */
export const PROJECT_SELECTOR_WIDTH = '18.75rem'

/**
 * Max height for the scrollable project list only (not counting a sticky footer row like
 * "Create project"). Uses `min(40vh, 28rem)` so the menu:
 * - stays under 40% of the viewport on short displays (never dominates the page), and
 * - caps at ~448px (28rem) on tall displays so it does not balloon unnecessarily.
 * Scales with root font size via the rem leg; the vh leg handles small windows.
 */
export const PROJECT_SELECTOR_LIST_MAX_HEIGHT = 'min(40vh, 28rem)'

export const projectSelectorUx = {
  /** Shown inline before the typeahead value in the masthead toggle. */
  togglePrefixLabel: 'Project:',
  allProjectsOptionLabel: 'All projects',
  allProjectsOptionDescription: 'View all items you have access to.',
  /** Shown on the toggle when `requireProject` is true and nothing is selected. */
  selectProjectPlaceholder: 'Select a project',
  /** Select group: starred projects (subset of current results), also listed under Projects. */
  favoritesGroupLabel: 'Favorites',
  /** Select group: full project list for the current typeahead / page (includes favorites). */
  projectsGroupLabel: 'Projects',
} as const

/**
 * Returns inline styles for the "Project:" prefix label in the project selector toggle.
 * When disabled, inherits the MenuToggle's disabled text color for proper contrast.
 * When enabled, uses regular text color (not subtle) for better contrast on the toggle background.
 */
export function getProjectTogglePrefixLabelStyle(isDisabled: boolean | undefined): CSSProperties {
  return {
    // When disabled, inherit PatternFly's disabled text color (--pf-v6-c-menu-toggle--disabled--Color).
    // When enabled, use regular text color for better contrast on MenuToggle's background.
    // (Subtle text color is designed for dark backgrounds; MenuToggle has light grey background in dark mode.)
    color: isDisabled ? 'inherit' : 'var(--pf-t--global--text--color--regular)',
    paddingInlineStart: 'var(--pf-t--global--spacer--control--horizontal--default)',
    paddingInlineEnd: 'var(--pf-t--global--spacer--xs)',
  }
}

/**
 * Handles `onChange` from the typeahead input, guarding against the spurious
 * event PF fires when the dropdown closes and the displayed value swaps from
 * `filterValue` back to `toggleLabel`.
 *
 * Extracted as a standalone function so the guard branches can be unit-tested
 * directly — PF's programmatic value swap cannot be replicated in happy-dom.
 */
export function handleTypeaheadChange(
  val: string,
  suppressRef: RefObject<boolean>,
  isOpen: boolean,
  updateFilter: (v: string) => void,
  setIsOpen: (open: boolean) => void
): void {
  if (suppressRef.current) {
    suppressRef.current = false
    if (!isOpen) return
  }
  updateFilter(val)
  if (!isOpen) setIsOpen(true)
}
