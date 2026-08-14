/**
 * Advanced loop and wait node helpers for v2 workflow E2E tests.
 * Extracted from v2-nodes.ts to keep file sizes within lint limits.
 */

import { expect, type Page } from '../fixtures'

import { openAddNodePanel, selectCategoryAndType } from './v2-nodes'
import { closeNodeEditorPanel, fillCodeEditor } from './workflows'

/**
 * Configure Loop node fields in an open form.
 * Supports both While and For Each loop types with all optional fields.
 *
 * @param page - Playwright page object
 * @param config - Loop configuration fields
 * @param config.name - Loop node name
 * @param config.type - Loop type (while or forEach) - switches between loop modes
 * @param config.condition - While loop condition expression (only applied when type='while' is also set)
 * @param config.items - For Each items expression
 * @param config.itemVariable - For Each item variable name
 * @param config.indexVariable - For Each index variable name
 * @param config.maxIterations - Maximum iterations limit
 *
 * @remarks
 * Important constraints:
 * - Setting `condition` requires `type: 'while'` in the same call
 * - Setting `items`, `itemVariable`, or `indexVariable` requires the form to already be in forEach mode
 *   or `type: 'forEach'` to be set in the same call
 */
export async function configureLoopNode(
  page: Page,
  config: {
    name?: string
    type?: 'while' | 'forEach'
    condition?: string
    items?: string
    itemVariable?: string
    indexVariable?: string
    maxIterations?: number
  }
) {
  if (config.name) {
    const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
    await expect(nameInput).toBeVisible()
    await nameInput.fill(config.name)
  }

  if (config.type) {
    const typeToggle = page.getByRole('button', { name: 'Type', exact: true })
    await expect(typeToggle).toBeVisible()
    await typeToggle.click()
    await page.getByRole('option', { name: config.type === 'while' ? 'While' : 'For each' }).click()
    // Wait for the type-specific field to appear, confirming the form re-rendered
    if (config.type === 'while') {
      await expect(page.getByLabel(/Expression editor mode/i)).toBeVisible()
    } else {
      await expect(page.getByRole('textbox', { name: 'Items expression', exact: true })).toBeVisible()
    }
  }

  // While-specific fields
  if (config.type === 'while' && config.condition !== undefined) {
    const editorModeToggle = page.getByLabel(/Expression editor mode/i)
    await expect(editorModeToggle).toBeVisible()
    await editorModeToggle.click()
    await page.getByRole('option', { name: 'Custom expression', exact: true }).click()

    const rawExpressionInput = page.getByLabel(/Raw expression/i)
    await expect(rawExpressionInput).toBeVisible()
    await rawExpressionInput.fill(config.condition)
  }

  // For Each-specific fields
  if (config.items !== undefined) {
    const itemsInput = page.getByRole('textbox', { name: 'Items expression', exact: true })
    await expect(itemsInput).toBeVisible({ timeout: 10_000 })
    await itemsInput.fill(config.items)
  }

  if (config.itemVariable !== undefined) {
    const itemVarInput = page.getByRole('textbox', { name: 'Item variable', exact: true })
    await expect(itemVarInput).toBeVisible({ timeout: 10_000 })
    await itemVarInput.fill(config.itemVariable)
    await expect(itemVarInput).toHaveValue(config.itemVariable)
  }

  if (config.indexVariable !== undefined) {
    const indexVarInput = page.getByRole('textbox', { name: 'Index variable', exact: true })
    await expect(indexVarInput).toBeVisible({ timeout: 10_000 })
    await indexVarInput.fill(config.indexVariable)
    await expect(indexVarInput).toHaveValue(config.indexVariable)
  }

  // Max iterations is common to both types
  if (config.maxIterations !== undefined) {
    const maxIterInput = page.getByRole('spinbutton', { name: /Max iterations/i })
    await expect(maxIterInput).toBeVisible()
    await maxIterInput.fill(String(config.maxIterations))
  }
}

/**
 * Save and close a node editor form.
 * Automatically detects "Create" (new nodes) or "Update" (editing) button.
 */
export async function saveAndCloseNodeForm(page: Page) {
  const createButton = page.getByRole('button', { name: 'Create', exact: true })
  const updateButton = page.getByRole('button', { name: 'Update', exact: true })

  // Check which button exists - Create for new nodes, Update for edits
  const buttonToClick = (await createButton.count()) > 0 ? createButton : updateButton

  await expect(buttonToClick).toBeVisible({ timeout: 10_000 })
  await expect(buttonToClick).toBeEnabled({ timeout: 10_000 })
  await buttonToClick.click()

  await expect(buttonToClick).not.toBeAttached({ timeout: 15_000 })
}

/**
 * Add a Loop (While) node with full configuration.
 */
export async function addWhileLoopNode(
  page: Page,
  config: {
    name: string
    condition: string
    maxIterations?: number
  }
) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Loop')

  await configureLoopNode(page, {
    type: 'while',
    ...config,
  })

  await saveAndCloseNodeForm(page)
}

/**
 * Add a Loop (For Each) node with full configuration.
 */
export async function addForEachLoopNode(
  page: Page,
  config: {
    name: string
    items: string
    itemVariable?: string
    indexVariable?: string
    maxIterations?: number
  }
) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Loop')

  await configureLoopNode(page, {
    type: 'forEach',
    ...config,
  })

  await saveAndCloseNodeForm(page)
}

/**
 * Add a script node as a child to the currently open loop body.
 * Assumes the add-node panel is already open or will be opened.
 */
export async function addChildScriptToLoop(page: Page, scriptName: string, code: string) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Action', 'Script')

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(scriptName)

  await fillCodeEditor(page, { value: code })
  await saveAndCloseNodeForm(page)
}

/**
 * Add a wait node (v2 type: "wait") with duration configuration.
 * Uses exact label strings ('Days', 'Hours', 'Minutes', 'Seconds') per UI-17.
 */
export async function addWaitNode(
  page: Page,
  name: string,
  durationConfig?: {
    seconds?: number
    minutes?: number
    hours?: number
    days?: number
  }
) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Wait')

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await expect(nameInput).toBeEditable({ timeout: 5_000 })
  await nameInput.fill(name)

  // Fill duration units with exact label strings
  if (durationConfig?.days !== undefined && durationConfig.days > 0) {
    await page.getByLabel('Days').fill(String(durationConfig.days))
  }
  if (durationConfig?.hours !== undefined && durationConfig.hours > 0) {
    await page.getByLabel('Hours').fill(String(durationConfig.hours))
  }
  if (durationConfig?.minutes !== undefined && durationConfig.minutes > 0) {
    await page.getByLabel('Minutes').fill(String(durationConfig.minutes))
  }
  if (durationConfig?.seconds !== undefined && durationConfig.seconds > 0) {
    await page.getByLabel('Seconds').fill(String(durationConfig.seconds))
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({ timeout: 15_000 })
  await closeNodeEditorPanel(page)
}
