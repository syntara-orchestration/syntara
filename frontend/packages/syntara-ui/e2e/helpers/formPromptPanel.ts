import type { Locator } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Activity row for a workflow node name. Row accessible names concatenate columns (`{name} Oct 14…`
 * or `{name} - submitted…` for the submitted-branch script). Require the first column to continue
 * with something other than ` -` so we do not match `{formStep} - submitted` rows.
 */
export function activityTableRowByActivityName(activityTable: Locator, activityName: string): Locator {
  const namePattern = new RegExp(`^${escapeRegExp(activityName)}(?:\\s+(?!-\\s).*)?$`)
  return activityTable.getByRole('row', { name: namePattern })
}

export function formStepDropdownField(app: Page, label: string): Locator {
  return app.getByRole('button', { name: label }).or(app.getByRole('combobox', { name: label }))
}

export async function expectFormStepDropdownOptions(
  app: Page,
  fieldLabel: string,
  optionLabels: string[]
): Promise<void> {
  const field = formStepDropdownField(app, fieldLabel)
  await field.click()
  const listbox = app.getByRole('listbox')
  for (const optionLabel of optionLabels) {
    const option = listbox
      .getByRole('option', { name: optionLabel })
      .or(listbox.getByRole('menuitem', { name: optionLabel }))
    await expect(option).toBeVisible()
  }
}

/** Per-step budget inside navigation retries (auto-detect can stomp panel index). */
export const FORM_PROMPT_NAV_STEP_TIMEOUT = 5_000

export async function openExecutionFormPromptDeepLink(
  app: Page,
  executionId: string,
  formPromptId: string,
  options?: { expectedMessage?: string }
): Promise<void> {
  const loadTimeout = process.env['SYNTARA_E2E_SKIP_WEB_SERVER'] ? 45_000 : 15_000
  await app.goto(toAppUrl(`/executions/${executionId}?form_prompt=${formPromptId}&history=closed`))
  await expect(app).toHaveURL(new RegExp(`form_prompt=${formPromptId}`))
  await expect(app.getByRole('heading', { name: 'Loading execution' })).toHaveCount(0, { timeout: loadTimeout })
  await waitForFormPromptPanel(app, { expectedMessage: options?.expectedMessage, timeout: loadTimeout })
}

export async function waitForFormPromptPanel(
  app: Page,
  options?: { timeout?: number; expectedMessage?: string }
): Promise<void> {
  const timeout = options?.timeout ?? 30_000
  await expect(app).toHaveURL(/form_prompt=/)
  await expect(app.getByRole('heading', { name: 'Respond to prompt' })).toBeVisible({ timeout })
  if (options?.expectedMessage) {
    await expect(app.getByText(options.expectedMessage)).toBeVisible({ timeout })
  }
}
