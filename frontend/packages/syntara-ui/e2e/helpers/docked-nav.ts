import type { Locator } from '@playwright/test'

import { expect, type Page } from '../fixtures'

/**
 * Playwright helpers for the PatternFly compass **docked** main navigation
 * (`AppDockedNav`, `aria-label="Main navigation"`).
 *
 * Multi-child sections (Configuration, System Administration) use `NavExpandable`:
 * a group toggle `button` reveals child routes as `link`s inside the nav — not
 * portaled flyout `menuitem`s. Specs that still target `menuitem` after clicking
 * Configuration will fail after the docked-nav refactor.
 *
 * Prefer `getByRole('link' | 'button')` scoped to {@link mainNavigation}; avoid
 * `.pf-v6-c-*` class selectors (see `patternfly.ts`).
 */

/** Locator for the docked sidebar nav landmark. */
export function mainNavigation(page: Page): Locator {
  return page.getByRole('navigation', { name: 'Main navigation' })
}

/**
 * Top-level nav group or single-destination entry (Configuration, System Administration, …).
 *
 * Use for visibility assertions. Prefer `listitem` (labeled `NavExpandable`) or a lone
 * `link` when the role only has one child — do not OR in the group toggle `button`; it
 * shares the group name with the parent `listitem` and triggers Playwright strict-mode
 * violations. Icon-only dock still labels the `listitem`; the expand control is unnamed.
 */
export function mainNavGroup(page: Page, groupName: string): Locator {
  const nav = mainNavigation(page)
  return nav
    .getByRole('listitem', { name: groupName, exact: true })
    .or(nav.getByRole('link', { name: groupName, exact: true }))
}

/** Click expand toggle — avoid scrolling `.or()` locators (Playwright can hang). */
async function clickDockedNavGroupToggle(page: Page, groupName: string): Promise<void> {
  const nav = mainNavigation(page)
  await mainNavGroup(page, groupName).scrollIntoViewIfNeeded()
  const namedButton = nav.getByRole('button', { name: groupName, exact: true })
  if (await namedButton.isVisible().catch(() => false)) {
    await namedButton.click()
    return
  }
  await nav.getByRole('listitem', { name: groupName, exact: true }).getByRole('button').click()
}

/**
 * Expand a docked nav group when its child links are not yet visible.
 *
 * @param probeChildName — a child link label known to appear when the group is open
 * (used to skip redundant toggles).
 */
export async function expandDockedNavGroup(page: Page, groupName: string, probeChildName: string): Promise<void> {
  const nav = mainNavigation(page)
  const childLink = nav.getByRole('link', { name: probeChildName, exact: true })

  if (await childLink.isVisible().catch(() => false)) {
    return
  }

  await clickDockedNavGroupToggle(page, groupName)
  await expect(childLink).toBeVisible()
}

/** Assert child route links are visible under an expanded group. */
export async function expectDockedNavGroupChildLinks(
  page: Page,
  groupName: string,
  childLinkNames: string[],
  probeChildName: string = childLinkNames[0]
): Promise<void> {
  await expandDockedNavGroup(page, groupName, probeChildName)
  const nav = mainNavigation(page)
  await Promise.all(childLinkNames.map((name) => expect(nav.getByRole('link', { name, exact: true })).toBeVisible()))
}

/**
 * Expand a nav group (if needed) and follow a child route link.
 *
 * Replaces legacy flyout helpers that clicked `menuitem` after Configuration /
 * System Administration.
 */
export async function navigateViaDockedNavGroup(page: Page, groupName: string, childLinkName: string): Promise<void> {
  await expandDockedNavGroup(page, groupName, childLinkName)
  const link = mainNavigation(page).getByRole('link', { name: childLinkName, exact: true })
  await link.scrollIntoViewIfNeeded()
  await link.click()
}

/**
 * Click a top-level nav entry that may render as a `link` (single destination)
 * or a group `button` (multiple children).
 */
export async function clickMainNavEntry(page: Page, label: string): Promise<void> {
  const nav = mainNavigation(page)
  const link = nav.getByRole('link', { name: label, exact: true })
  if (await link.isVisible().catch(() => false)) {
    await link.scrollIntoViewIfNeeded()
    await link.click()
    return
  }

  const listItem = nav.getByRole('listitem', { name: label, exact: true })
  const listItemLink = listItem.getByRole('link')
  if (await listItemLink.isVisible().catch(() => false)) {
    await listItemLink.scrollIntoViewIfNeeded()
    await listItemLink.click()
    return
  }

  await clickDockedNavGroupToggle(page, label)
}

/** Convenience wrapper for Configuration → child (Integrations, Credentials, …). */
export async function navigateViaConfigurationMenu(page: Page, childLinkName: string): Promise<void> {
  await navigateViaDockedNavGroup(page, 'Configuration', childLinkName)
}

/** Convenience wrapper for System Administration → child. */
export async function navigateViaSystemAdministrationMenu(page: Page, childLinkName: string): Promise<void> {
  await navigateViaDockedNavGroup(page, 'System Administration', childLinkName)
}
