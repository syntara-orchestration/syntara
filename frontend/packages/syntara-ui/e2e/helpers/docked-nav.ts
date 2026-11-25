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

function mainNavGroupListItem(page: Page, groupName: string): Locator {
  return mainNavigation(page).getByRole('listitem', { name: groupName, exact: true })
}

function mainNavGroupLink(page: Page, groupName: string): Locator {
  return mainNavigation(page).getByRole('link', { name: groupName, exact: true })
}

const NAV_CHILD_LINK_TIMEOUT_MS = 15_000
const NAV_TOGGLE_TIMEOUT_MS = 5_000

/** Scroll a single stable node into view — never call `scrollIntoViewIfNeeded` on `.or()` locators. */
async function scrollDockedNavGroupIntoView(page: Page, groupName: string): Promise<void> {
  const nav = mainNavigation(page)
  await expect(nav).toBeVisible()

  const listItem = mainNavGroupListItem(page, groupName)
  if ((await listItem.count()) > 0) {
    await expect(listItem).toBeVisible()
    await listItem.scrollIntoViewIfNeeded()
    return
  }

  const link = mainNavGroupLink(page, groupName)
  await expect(link).toBeVisible()
  await link.scrollIntoViewIfNeeded()
}

/** @returns whether an expand control was clicked */
async function tryClickDockedNavGroupToggle(page: Page, groupName: string): Promise<boolean> {
  await scrollDockedNavGroupIntoView(page, groupName)

  const nav = mainNavigation(page)
  const listItem = mainNavGroupListItem(page, groupName)
  if ((await listItem.count()) > 0) {
    const expandButton = listItem.getByRole('button')
    try {
      await expect(expandButton).toBeVisible({ timeout: NAV_TOGGLE_TIMEOUT_MS })
      await expandButton.click()
      return true
    } catch {
      // NavExpandable may render expanded with no toggle button (see AppDockedNav isExpanded).
    }
  }

  const namedButton = nav.getByRole('button', { name: groupName, exact: true })
  try {
    await expect(namedButton).toBeVisible({ timeout: NAV_TOGGLE_TIMEOUT_MS })
    await namedButton.click()
    return true
  } catch {
    return false
  }
}

async function clickDockedNavGroupToggle(page: Page, groupName: string): Promise<void> {
  const clicked = await tryClickDockedNavGroupToggle(page, groupName)
  if (!clicked) {
    throw new Error(`No expand toggle found for docked nav group "${groupName}"`)
  }
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

  try {
    await expect(childLink).toBeVisible({ timeout: NAV_CHILD_LINK_TIMEOUT_MS })
    return
  } catch {
    // Child not visible yet — try toggle, or group may already be expanded without a toggle.
  }

  const toggled = await tryClickDockedNavGroupToggle(page, groupName)
  if (!toggled) {
    await scrollDockedNavGroupIntoView(page, groupName)
  }

  await expect(childLink).toBeVisible({ timeout: NAV_CHILD_LINK_TIMEOUT_MS })
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
  await expect(link).toBeVisible()
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
