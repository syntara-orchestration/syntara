import type { Locator } from '@playwright/test'

import { type Page, expect } from '../fixtures'

/**
 * Reset layout and fit view so all nodes are in the viewport (required in CI).
 * Skips each toolbar action when its button is absent. Relies on Playwright auto-wait
 * after fit view — no fixed sleeps.
 *
 * Use {@link triggerLayout} in `workflows.ts` when you only need nodes repositioned after
 * adding steps (reset only, no fit view). Use `layoutCanvas` when tests must also fit the
 * viewport (typical in CI) before clicking nodes or edge controls.
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

export function canvasStepNode(page: Page, stepName: string) {
  return page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: stepName })
}

/**
 * Open the three-panel step editor from the canvas. SynStep nodes use the header Edit
 * control; generic placeholder nodes still open on body click.
 */
export async function clickCanvasStepToOpenEditor(stepElement: Locator, stepName: string) {
  const editButton = stepElement.getByRole('button', { name: `Edit ${stepName}`, exact: true })
  if ((await editButton.count()) > 0) {
    await editButton.click({ timeout: 5_000 })
    return
  }
  await stepElement.click({ timeout: 5_000 })
}

/**
 * Click a workflow step on the React Flow canvas and wait for its editor to open.
 *
 * Retrying the open matches {@link openStepForEditing} in `workflows.ts`: under CI load
 * the click can land while the viewport is still transforming. The success condition is
 * the editor showing this step — the Name field carries the clicked step's name.
 */
export async function clickStep(page: Page, stepName: string) {
  await layoutCanvas(page)
  const node = canvasStepNode(page, stepName)
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(async () => {
    await expect(node).toBeVisible({ timeout: 5_000 })
    await clickCanvasStepToOpenEditor(node, stepName)
    await expect(nameInput).toHaveValue(stepName, { timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })
}

/** @deprecated Prefer `clickStep`; kept for older specs importing `clickNode`. */
export const clickNode = clickStep
