/**
 * Canvas "Add connected step" stub clicks.
 * Extracted from workflows.ts to stay within eslint max-lines.
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

async function waitForCanvasIdle(page: Page) {
  await expect(page.locator('.pf-v6-c-alert-group [data-ouia-component-type="PF6/Alert"]'))
    .toHaveCount(0, { timeout: 5000 })
    .catch(() => {})
  await expect(page.getByLabel('Loading'))
    .toHaveCount(0, { timeout: 10000 })
    .catch(() => {})
}

async function revealConnectedStepButtons(page: Page) {
  await waitForCanvasIdle(page)
  await expect(page.getByRole('button', { name: 'Create', exact: true }))
    .not.toBeAttached({ timeout: 10_000 })
    .catch(() => {})
  const layoutButton = page.getByRole('button', { name: 'Reset layout', exact: true })
  await expect(layoutButton).toBeVisible({ timeout: 10_000 })
  await layoutButton.click()
  const fitViewButton = page.getByRole('button', { name: 'Fit view' })
  if ((await fitViewButton.count()) > 0) await fitViewButton.click()
  await expect(page.locator('[role="group"][aria-roledescription="node"]')).not.toHaveCount(0, { timeout: 10_000 })
  await waitForCanvasIdle(page)
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

/** Layout + fit view, then click an edge "Add connected step" button and return the add-node panel. */
export async function clickAddConnectedStep(page: Page, preferredHandle?: string) {
  await revealConnectedStepButtons(page)
  const addBtn = page.getByRole('button', { name: 'Add connected step' })
  await expect(addBtn).not.toHaveCount(0, { timeout: 25_000 })
  await expect(async () => {
    const stubMissing = preferredHandle
      ? (await page.getByTestId(`add-node-button-${preferredHandle}`).count()) !== 1
      : (await addBtn.count()) === 0
    if (stubMissing) await revealConnectedStepButtons(page)
    const clicked = await clickUniqueStub(page, preferredHandle)
    if (!clicked) {
      // Never click a multi-match role locator (strict mode).
      await expect(addBtn).toHaveCount(1)
      await addBtn.click({ force: true, timeout: 5_000 })
    }
    await expect(addNodePanel(page)).toHaveCount(1)
  }).toPass({ timeout: 15_000, intervals: [500, 1_000] })
  const panel = addNodePanel(page)
  await expect(panel.getByRole('button', { name: 'Action', exact: true })).toBeVisible({ timeout: 15_000 })
  return panel
}
