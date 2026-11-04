import { expect, type Page } from '../fixtures'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'
import { apiRequest } from '../utils/api'

import { clickWhenEnabled, pfWidget } from './patternfly'

/** True when Playwright targets a live API (compose / podman E2E), not the in-process mock. */
export const isRealBackendE2e = isSkipWebServerForPlaywrightTests()

const FORM_STEP_SUBMIT_WAIT_MS = 45_000

/** Responder allow-list entries must match the logged-in user's id (JWT /auth/me). */
export async function currentUserResponderRef(app: Page): Promise<{ id: string; username: string }> {
  const resp = await apiRequest(app, 'get', '/auth/me')
  expect(resp.ok()).toBeTruthy()
  const body = (await resp.json()) as { id: string; username?: string }
  return { id: body.id, username: body.username ?? 'admin' }
}

/** Workflow publish schema stores responder usernames (not ids). */
export function responderUsernameAllowList(username: string): string[] {
  return [username]
}

export async function submitOpenFormStepAndExpectSuccess(app: Page, formPromptId: string): Promise<void> {
  await expect(async () => {
    const fpResp = await apiRequest(app, 'get', `/form_prompts/${formPromptId}`)
    expect(fpResp.ok()).toBeTruthy()
    const prompt = (await fpResp.json()) as { status?: string; submit_label?: string | null }
    expect(prompt.status).toBe('pending')

    const submitLabel =
      typeof prompt.submit_label === 'string' && prompt.submit_label.trim().length > 0
        ? prompt.submit_label.trim()
        : 'Submit'
    const submitButton = app.getByRole('button', { name: submitLabel })
    await expect(submitButton).toBeVisible({ timeout: 15_000 })
    await clickWhenEnabled(submitButton, { timeout: 15_000 })
  }).toPass({ timeout: FORM_STEP_SUBMIT_WAIT_MS, intervals: [500, 1_000, 2_000] })

  await expect(pfWidget(app, 'Alert').filter({ hasText: 'Form submitted' })).toBeVisible({
    timeout: FORM_STEP_SUBMIT_WAIT_MS,
  })
}

/** Non-responders get read-only fields; submit is hidden (see FormPromptResponseContent). */
export async function expectFormStepReadOnlyForNonResponder(page: Page, fieldLabel = 'Answer'): Promise<void> {
  await expect(page.getByRole('heading', { name: 'Respond to prompt' })).toBeVisible({ timeout: 20_000 })
  const field = page.getByRole('textbox', { name: fieldLabel })
  await expect(field).toBeDisabled({ timeout: 20_000 })
  await field.hover()
  await expect(page.getByRole('tooltip').filter({ hasText: /not configured as a responder/i })).toBeVisible({
    timeout: 10_000,
  })
  await expect(page.getByRole('button', { name: 'Submit response' })).not.toBeVisible()
}

export async function expectDangerToast(
  page: Page,
  title: string,
  descriptionFragment?: string | RegExp
): Promise<void> {
  const alert = page.getByRole('alert').filter({ hasText: title })
  await expect(alert).toBeVisible({ timeout: 15_000 })
  if (descriptionFragment !== undefined) {
    await expect(alert).toContainText(descriptionFragment)
  }
}
