/**
 * Converge node helpers for v2 workflow E2E tests.
 * Extracted from v2-nodes.ts to keep file sizes within lint limits.
 */

import { expect, type Page, toAppUrl } from '../fixtures'

import { addConditionNodeWithBranch, addManualTrigger, openAddNodePanel, selectCategoryAndType } from './v2-nodes'
import { buildUniqueName, closeNodeEditorPanel } from './workflows'

/**
 * Navigate to a new workflow, add trigger + condition, and open the converge form.
 * Used by validation-only tests that don't need to save the workflow.
 */
export async function openConvergeFormOnNewWorkflow(page: Page) {
  await page.goto(toAppUrl('/workflow-builder/new'))
  await addManualTrigger(page, 'Manual trigger')
  await addConditionNodeWithBranch(page, 'Condition', 'true')
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Converge')
}

/** Add a converge node (v2 type: "converge"). */
export async function addConvergeNode(page: Page, name: string) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Converge')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add a converge node with 'all' strategy (wait for all branches).
 * V2 type: "converge", strategy: "all"
 */
export async function addConvergeNodeWithAllStrategy(page: Page, name: string) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Converge')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  // Strategy defaults to 'all', so no need to change it
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add a converge node with 'any' strategy (wait for N of M branches).
 * V2 type: "converge", strategy: "any", requiredPathCount: number
 */
export async function addConvergeNodeWithAnyStrategy(page: Page, name: string, requiredPathCount: number) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Converge')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)

  // Select 'any' strategy via PF Select (click toggle, then option)
  await page.getByRole('button', { name: 'Continue when criteria', exact: true }).click()
  await page.getByRole('option', { name: 'Any branches reach this step' }).click()

  // Fill required path count
  const requiredPathCountInput = page.getByRole('spinbutton', {
    name: /Required number of branches before continuing/i,
  })
  await expect(requiredPathCountInput).toBeVisible()
  await requiredPathCountInput.fill(String(requiredPathCount))

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add a converge node with wait_duration configuration.
 * V2 type: "converge", wait_duration stored in config (Parameters tab).
 * The `action` param is accepted for API compatibility but ignored — on_timeout
 * no longer exists; use the Settings tab continue_on_failure instead.
 */
export async function addConvergeNodeWithTimeout(
  page: Page,
  name: string,
  timeoutConfig: {
    seconds?: number
    minutes?: number
    hours?: number
    days?: number
    action?: 'fail' | 'continue'
    strategy?: 'all' | 'any'
    requiredPathCount?: number
  }
) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Converge')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)

  // Set strategy if provided
  if (timeoutConfig.strategy === 'any' && timeoutConfig.requiredPathCount !== undefined) {
    await page.getByRole('button', { name: 'Continue when criteria', exact: true }).click()
    await page.getByRole('option', { name: 'Any branches reach this step' }).click()
    const requiredPathCountInput = page.getByRole('spinbutton', {
      name: /Required number of branches before continuing/i,
    })
    await expect(requiredPathCountInput).toBeVisible()
    await requiredPathCountInput.fill(String(timeoutConfig.requiredPathCount))
  }

  // Fill wait_duration units — DurationInput is always visible in Parameters tab
  if (timeoutConfig.seconds !== undefined) {
    await page.getByLabel(/Seconds/i).fill(String(timeoutConfig.seconds))
  }
  if (timeoutConfig.minutes !== undefined) {
    await page.getByLabel(/Minutes/i).fill(String(timeoutConfig.minutes))
  }
  if (timeoutConfig.hours !== undefined) {
    await page.getByLabel(/Hours/i).fill(String(timeoutConfig.hours))
  }
  if (timeoutConfig.days !== undefined) {
    await page.getByLabel(/Days/i).fill(String(timeoutConfig.days))
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Create a workflow with trigger and condition node (2 branches), ready for converge node testing.
 * Returns the unique workflow name.
 */
export async function createWorkflowWithBranchesForConverge(page: Page): Promise<string> {
  const workflowName = buildUniqueName('converge-test')

  // Start on /workflow-builder/new
  await page.goto(toAppUrl('/workflow-builder/new'))

  // Add manual trigger
  await addManualTrigger(page, 'Manual trigger')

  // Add condition node with branch (creates 2 branches: true and false)
  await addConditionNodeWithBranch(page, 'Condition', 'true')

  return workflowName
}

/**
 * Verify converge node configuration in saved V2 workflow payload.
 * Uses snake_case field names as they appear in the API payload.
 */
export function expectConvergeNodeConfig(
  nodes: Array<{ id: string; type: string; parameters: Record<string, unknown> }>,
  expected: {
    strategy: 'all' | 'any'
    n_required?: number
    wait_duration?: number
    /** @deprecated on_timeout removed from schema; use Settings tab continue_on_failure */
    on_timeout?: 'fail' | 'continue'
    /** @deprecated timeout renamed to wait_duration */
    timeout?: number
  }
) {
  const convergeNode = nodes.find((n) => n.type === 'converge')
  expect(convergeNode).toBeDefined()
  expect(convergeNode?.parameters.strategy).toBe(expected.strategy)

  if (expected.n_required !== undefined) {
    expect(convergeNode?.parameters.n_required).toBe(expected.n_required)
  } else {
    expect(convergeNode?.parameters.n_required).toBeUndefined()
  }

  const expectedDuration = expected.wait_duration ?? expected.timeout
  if (expectedDuration !== undefined) {
    expect(convergeNode?.parameters.wait_duration).toBe(expectedDuration)
  } else {
    expect(convergeNode?.parameters.wait_duration).toBeUndefined()
  }
}
