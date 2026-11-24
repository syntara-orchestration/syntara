/**
 * Project selection helpers for the workflow builder.
 *
 * New workflows pick their project in the "Select a project" modal shown on
 * `/workflow-builder/new` ({@link openNewWorkflowBuilder}); the builder toolbar
 * shows the chosen project as text. Re-exported from `./workflows`.
 */
import type { Locator } from '@playwright/test'

import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../src/constants/viewport'
import { expect, type Page, toAppUrl } from '../fixtures'

import { waitForUIReady } from './ui-ready'

/**
 * Select the first available project from a typeahead project selector dropdown.
 * Works on both mock API (where projects are available immediately) and real backend
 * (where project names vary). Skips "All projects" and "Create project" options.
 */
export async function selectFirstProject(page: Page) {
  const projectInput = page.getByPlaceholder(/All projects|Select a project/)
  const hasInput = await projectInput
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!hasInput) return

  await projectInput.click()
  await page.getByRole('option').first().waitFor({ state: 'visible', timeout: 10_000 })

  // Retry until a real project option appears — API-loaded options arrive after
  // static ones ("All projects", "Create project") on slower CI backends.
  await clickFirstRealProjectOption(page)

  // Wait for the "Select a project" placeholder to disappear before returning.
  // Use not.toBeVisible (not not.toHaveAttribute) because the element may be
  // removed from the DOM entirely after selection, which causes toHaveAttribute
  // to throw "element(s) not found".
  await expect(page.getByPlaceholder('Select a project')).not.toBeVisible()
}

/** Escape a literal string for embedding in a RegExp. */
function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Legacy: select a project in the builder toolbar.
 *
 * The builder toolbar no longer has a project selector — the project is chosen
 * in the "Select a project" modal before the canvas opens (see
 * {@link openNewWorkflowBuilder}) and the toolbar only shows "Project: <name>"
 * as text. Once the builder is open there is no "Select a project" placeholder,
 * so this returns after its short probe. Kept so existing call sites stay
 * harmless; to pick a specific project pass `projectName` to
 * {@link openNewWorkflowBuilder} instead.
 */
export async function selectProjectIfRequired(page: Page, projectName?: string) {
  const projectInput = page.getByPlaceholder(/Select a project/)
  // Use a short timeout — if the project is already selected ("default" shows
  // in the toggle with no "Select a project" placeholder), the element will
  // never appear and a 15s wait burns most of the test budget unnecessarily.
  const needsSelection = await projectInput
    .waitFor({ state: 'visible', timeout: 2_000 })
    .then(() => true)
    .catch(() => false)
  if (!needsSelection) return

  // The placeholder is briefly "Select a project" before the Zustand store
  // restores a previously selected project and re-renders the toggle.
  // Re-check that the locator still matches; if it vanished, a project is
  // already selected and no action is needed.
  if ((await projectInput.count()) === 0) return

  // On saved workflows the project selector is disabled (project already assigned).
  if (!(await projectInput.isEnabled())) return

  await projectInput.click()
  await page.getByRole('option').first().waitFor({ state: 'visible', timeout: 10_000 })

  if (projectName) {
    // Anchor at the start of the option's accessible name. Each option reads
    // "<name> <description>", so a plain substring match for `default` also
    // matches the built-in project's "Default project for ..." description and
    // resolves to two elements.
    const option = page.getByRole('option', { name: new RegExp(`^${escapeForRegExp(projectName)}(\\s|$)`) })
    await option.waitFor({ state: 'visible', timeout: 15_000 })
    await option.click()
  } else {
    await clickFirstRealProjectOption(page)
  }
}

/** The project typeahead used by toolbar project pickers when no narrower toggle is passed. */
const defaultProjectToggle = (page: Page): Locator => page.getByPlaceholder(/All projects|Select a project/)

async function clickFirstRealProjectOption(page: Page, toggle: Locator = defaultProjectToggle(page)) {
  // First try: wait for an API-loaded project to appear
  const found = await trySelectRealProject(page, toggle)
  if (found) return

  // No real projects exist — create one via the "Create project" UI option
  await createProjectViaDropdown(page, toggle)
}

async function trySelectRealProject(page: Page, toggle: Locator): Promise<boolean> {
  try {
    await expect(async () => {
      const options = page.getByRole('option')
      if ((await options.count()) === 0) {
        if ((await toggle.count()) > 0) await toggle.click()
        await options.first().waitFor({ state: 'visible', timeout: 3_000 })
      }

      // Prefer `default` — the project `ensureProject` guarantees, and the only
      // one no spec deletes. Taking whatever sorts first instead means picking a
      // project another worker created and is about to clean up: the builder
      // holds its id, the delete lands, and the save then fails with
      // `404 {"detail":"Project <id> not found"}`. That was invisible before
      // saves were gated on the response, because the weak URL guard passed
      // regardless.
      //
      // Matched on the *accessible* name, not `textContent`. The option renders
      // name and description as adjacent nodes with no separator, so
      // `textContent` reads `defaultDefault project` and no anchored match on it
      // can work; the accessible name joins them with a space. Anchoring matters
      // either way — a bare `default` also matches the built-in project's
      // "Default project for built-in workflows" description.
      const preferred = page.getByRole('option', { name: /^default(\s|$)/ })
      if ((await preferred.count()) === 1) {
        await preferred.click()
        return
      }

      const allOptions = await options.all()
      for (const option of allOptions) {
        const text = await option.textContent()
        if (
          text &&
          !text.includes('All projects') &&
          !text.includes('Create project') &&
          !text.toLowerCase().includes('built-in')
        ) {
          await option.click()
          return
        }
      }
      throw new Error('No real project options yet')
    }).toPass({ timeout: 15_000 })
    return true
  } catch {
    return false
  }
}

async function createProjectViaDropdown(page: Page, toggle: Locator) {
  const options = page.getByRole('option')
  if ((await options.count()) === 0) {
    if ((await toggle.count()) > 0) await toggle.click()
    await options.first().waitFor({ state: 'visible', timeout: 5_000 })
  }

  await page.getByRole('option', { name: 'Create project' }).click()

  // Scope to the create-project dialog: it can open on top of the
  // "Select a project" modal, so a bare getByRole('dialog') would match two.
  const dialog = page.getByRole('dialog').filter({ has: page.getByRole('textbox', { name: 'Project name' }) })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('textbox', { name: 'Project name' }).fill('default')
  await dialog.getByRole('button', { name: 'Create project' }).click()

  // Wait for dialog to close (project created)
  await expect(dialog).not.toBeVisible({ timeout: 15_000 })
}

/** The "Select a project" modal shown when opening `/workflow-builder/new`. */
export const selectProjectDialog = (page: Page): Locator => page.getByRole('dialog', { name: 'Select a project' })

/**
 * Pick a project in the "Select a project" modal unless it is already pre-filled.
 *
 * Pre-fill comes from `?projectId=` or from the user having exactly one
 * non-built-in project; both land after the project list loads, so each case
 * waits for it before deciding to choose.
 */
async function chooseProjectInModal(
  page: Page,
  { projectName, projectId }: { projectName?: string; projectId?: string }
) {
  const dialog = selectProjectDialog(page)
  const projectInput = dialog.getByLabel('Project', { exact: true })
  const continueButton = dialog.getByRole('button', { name: 'Continue', exact: true })
  await expect(projectInput).toBeVisible({ timeout: 15_000 })

  if (projectName) {
    const prefilled = await expect(projectInput)
      .toHaveValue(projectName, { timeout: projectId ? 10_000 : 3_000 })
      .then(() => true)
      .catch(() => false)
    if (prefilled) return

    // Typing the name filters the typeahead, which also clears a different
    // pre-filled project. Anchor the match: options read "<name> <description>".
    await projectInput.fill(projectName)
    const option = page.getByRole('option', { name: new RegExp(`^${escapeForRegExp(projectName)}(\\s|$)`) })
    await option.waitFor({ state: 'visible', timeout: 15_000 })
    await option.click()
    return
  }

  if (projectId) {
    // `?projectId=` must pre-select; never silently fall back to another project.
    await expect(continueButton).toBeEnabled({ timeout: 15_000 })
    return
  }

  const prefilled = await expect(continueButton)
    .toBeEnabled({ timeout: 3_000 })
    .then(() => true)
    .catch(() => false)
  if (prefilled) return

  await projectInput.click()
  await clickFirstRealProjectOption(page, projectInput)
}

/**
 * Complete the "Select a project" modal that `/workflow-builder/new` shows
 * before the canvas, then wait for the builder.
 *
 * Use directly after clicking a "Create workflow" button; use
 * {@link openNewWorkflowBuilder} to navigate there first. Picks `projectName`
 * when given; otherwise keeps a pre-filled project (from the URL's
 * `?projectId=` or the single-project default) or picks the first real project.
 */
export async function confirmNewWorkflowProject(
  page: Page,
  { projectName }: { projectName?: string } = {}
): Promise<void> {
  const dialog = selectProjectDialog(page)
  await expect(dialog).toBeVisible({ timeout: 15_000 })

  const projectId = new URL(page.url()).searchParams.get('projectId') ?? undefined
  await chooseProjectInModal(page, { projectName, projectId })

  const continueButton = dialog.getByRole('button', { name: 'Continue', exact: true })
  await expect(continueButton).toBeEnabled({ timeout: 10_000 })
  await continueButton.click()

  await expect(dialog).not.toBeVisible({ timeout: 15_000 })
  await expect(page).toHaveURL(/\/workflow-builder\/new\?(?:.*&)?projectId=[^&#]+/, { timeout: 15_000 })
  // Below the minimum supported width the builder renders a "larger screen
  // is needed" empty state instead of the toolbar; either means it is ready.
  const builderReady = page
    .getByPlaceholder('Workflow name')
    .or(page.getByRole('heading', { level: 2, name: REACT_FLOW_VIEWPORT_EMPTY_STATE.title }))
  // Narrow viewports can render both (the name input stays in the DOM behind the
  // empty state), so wait for at least one rather than exactly one.
  await expect(builderReady.filter({ visible: true })).not.toHaveCount(0, { timeout: 15_000 })
  await waitForUIReady(page)
}

/**
 * Open the builder for a new workflow.
 *
 * `/workflow-builder/new` first shows the "Select a project" modal; the canvas
 * only renders after a project is chosen and Continue is clicked, at which
 * point the URL carries `?projectId=`. Navigates there (with `?projectId=`
 * when given, which must pre-fill the modal) and drives the modal with
 * {@link confirmNewWorkflowProject}.
 */
export async function openNewWorkflowBuilder(
  page: Page,
  { projectName, projectId }: { projectName?: string; projectId?: string } = {}
): Promise<void> {
  const path = projectId ? `/workflow-builder/new?projectId=${encodeURIComponent(projectId)}` : '/workflow-builder/new'
  await page.goto(toAppUrl(path))
  await confirmNewWorkflowProject(page, { projectName })
}
