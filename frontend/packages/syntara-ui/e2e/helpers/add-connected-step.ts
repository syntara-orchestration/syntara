/**
 * Canvas "Add connected step" stub clicks.
 * Extracted from workflows.ts to stay within eslint max-lines.
 *
 * Stubs are SVG <rect role="button"> with data-testid `add-node-button-${handle}`.
 * The accessible name can be missing while the testid is already in the DOM, so
 * presence waits use testid. Role is only a fallback click when it matches exactly
 * once (strict mode).
 *
 * Fit view is retried inside toPass — Reset layout remounts nodes and must not run
 * as a one-shot before a long locator wait.
 */

import { type Page, expect } from '../fixtures'

const addNodePanel = (page: Page) =>
  page.getByRole('region', {
    name: /add step|select an action node|select a trigger node|select a logic node|select an aap execution node/i,
  })

/**
 * Prefer unique happy-path stubs so unused condition `false` is never clicked
 * together with loop `done` (Playwright strict mode). Loop body is `loop`
 * (v2 port `iterate`), not `iterate`.
 */
const STUB_PRIORITY = ['approved', 'true', 'loop', 'iterate', 'source', 'done'] as const

const CANVAS_NODE = '[role="group"][aria-roledescription="node"]'
const CREATE_DETACH_TIMEOUT = 10_000
const STUB_RETRY_TIMEOUT = 25_000
const RETRY_ASSERT_TIMEOUT = 1_000

async function waitForCanvasIdle(page: Page) {
  await expect(page.locator('.pf-v6-c-alert-group [data-ouia-component-type="PF6/Alert"]'))
    .toHaveCount(0, { timeout: 2_000 })
    .catch(() => {})
  await expect(page.getByLabel('Loading'))
    .toHaveCount(0, { timeout: 3_000 })
    .catch(() => {})
}

function addNodeStubs(page: Page, preferredHandle?: string) {
  return preferredHandle
    ? page.getByTestId(`add-node-button-${preferredHandle}`)
    : page.locator('[data-testid^="add-node-button-"]')
}

async function clickNamedControl(page: Page, name: string) {
  const button = page.getByRole('button', { name, exact: true })
  if ((await button.count()) === 1) await button.click()
}

async function revealConnectedStepStubs(page: Page, preferredHandle?: string) {
  await waitForCanvasIdle(page)
  await clickNamedControl(page, 'Fit view')
  const stubs = addNodeStubs(page, preferredHandle)
  if ((await stubs.count()) > 0) return stubs
  // Last resort: Reset layout remounts nodes. Only after Fit view left stubs missing.
  await clickNamedControl(page, 'Reset layout')
  await waitForCanvasIdle(page)
  await clickNamedControl(page, 'Fit view')
  return stubs
}

async function clickUniqueStub(page: Page, preferredHandle?: string): Promise<boolean> {
  const handles = preferredHandle ? [preferredHandle] : STUB_PRIORITY
  for (const handle of handles) {
    const port = page.getByTestId(`add-node-button-${handle}`)
    if ((await port.count()) === 1) {
      await port.click({ force: true, timeout: 5_000 })
      return true
    }
  }
  return false
}

async function clickRoleFallback(page: Page) {
  const addBtn = page.getByRole('button', { name: 'Add connected step' })
  // Never click a multi-match role locator (strict mode).
  await expect(addBtn).toHaveCount(1)
  await addBtn.click({ force: true, timeout: 5_000 })
}

async function clickStubAndOpenPanel(page: Page, preferredHandle?: string) {
  const panel = addNodePanel(page)
  if ((await panel.count()) === 1) return

  const stubs = await revealConnectedStepStubs(page, preferredHandle)
  await expect(page.locator(CANVAS_NODE)).not.toHaveCount(0, { timeout: RETRY_ASSERT_TIMEOUT })
  await expect(stubs).not.toHaveCount(0, { timeout: RETRY_ASSERT_TIMEOUT })

  const clicked = await clickUniqueStub(page, preferredHandle)
  if (!clicked) await clickRoleFallback(page)
  await expect(panel).toHaveCount(1)
}

/** Fit view (retrying), then click an edge add-step stub and return the add-node panel. */
export async function clickAddConnectedStep(page: Page, preferredHandle?: string) {
  await expect(page.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({
    timeout: CREATE_DETACH_TIMEOUT,
  })
  await expect(async () => {
    await clickStubAndOpenPanel(page, preferredHandle)
  }).toPass({ timeout: STUB_RETRY_TIMEOUT, intervals: [500, 1_000] })
  const panel = addNodePanel(page)
  await expect(panel.getByRole('button', { name: 'Action', exact: true })).toBeVisible({ timeout: 15_000 })
  return panel
}
