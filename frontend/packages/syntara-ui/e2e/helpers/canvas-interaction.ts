import { type Page, expect } from '../fixtures'

/**
 * Reset layout and fit view so all nodes are in the viewport (required in CI).
 * Skips each toolbar action when its button is absent. Relies on Playwright auto-wait
 * after fit view — no fixed sleeps.
 *
 * Use {@link triggerLayout} in `workflows.ts` when you only need nodes repositioned after
 * adding steps (reset only, no fit view). Use `layoutCanvas` before clicking nodes or
 * edge controls when the full viewport must be visible under CI.
 */
export async function layoutCanvas(page: Page) {
  const layoutButton = page.getByRole('button', { name: 'Reset layout', exact: true })
  if ((await layoutButton.count()) > 0) {
    await layoutButton.click()
    await page.waitForSelector('[role="group"][aria-roledescription="node"]', { state: 'visible', timeout: 5_000 })
  }
  const fitViewButton = page.getByRole('button', { name: 'Fit view' })
  if ((await fitViewButton.count()) > 0) {
    await fitViewButton.click()
  }
}

/**
 * Click a React Flow node by its visible text label and wait for its editor to open.
 *
 * Retrying the open matches {@link openNodeForEditing} in `workflows.ts`: under CI load
 * the click can land while the viewport is still transforming. The success condition is
 * the editor showing this node — the Name field carries the clicked node's name.
 */
export async function clickNode(page: Page, nodeText: string) {
  await layoutCanvas(page)
  const node = page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeText })
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(async () => {
    await expect(node).toBeVisible({ timeout: 5_000 })
    await node.click({ timeout: 5_000 })
    await expect(nameInput).toHaveValue(nodeText, { timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })
}
