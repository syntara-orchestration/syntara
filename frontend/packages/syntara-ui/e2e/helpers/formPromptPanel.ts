import { expect, type Page, toAppUrl } from '../fixtures'

/** Per-step budget inside navigation retries (auto-detect can stomp panel index). */
export const FORM_PROMPT_NAV_STEP_TIMEOUT = 5_000

export async function openExecutionFormPromptDeepLink(
  app: Page,
  executionId: string,
  formPromptId: string,
  options?: { expectedMessage?: string }
): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}?form_prompt=${formPromptId}&history=closed`))
  await expect(app).toHaveURL(new RegExp(`form_prompt=${formPromptId}`))
  await waitForFormPromptPanel(app, { expectedMessage: options?.expectedMessage })
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
