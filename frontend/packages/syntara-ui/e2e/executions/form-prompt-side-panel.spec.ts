/**
 * E2E: Execution detail — form step response side panel
 *
 * Critical paths covered:
 * - Deep link, activity row, and toolbar entry into the respond panel
 * - Required-field validation, dynamic dropdown options, expired response window
 * - Submit success/error, read-only submitted state, viewer without submit permission
 * - Previous/next navigation between prompts on the same execution
 *
 * Mock seed: syntara-mock-api/src/resources/formPrompts.ts (exec-form-prompt).
 */
import { createUnavailableGuard, test, expect, toAppUrl, type Page } from '../fixtures'
import {
  FORM_PROMPT_NAV_STEP_TIMEOUT,
  openExecutionFormPromptDeepLink,
  waitForFormPromptPanel,
} from '../helpers/formPromptPanel'
import { createPendingFormPromptLight, MOCK_FORM_RESPONSE_SEED } from '../helpers/formResponses'
import { clickWhenEnabled, pfWidget } from '../helpers/patternfly'
import { apiRequest, deleteWorkflowViaApi } from '../utils/api'

const SEED = MOCK_FORM_RESPONSE_SEED

test.describe('Execution detail — Form step side panel', { tag: '@pr-check' }, () => {
  const seedGuard = createUnavailableGuard(
    'Form step execution seed required (see syntara-mock-api formPrompts / exec-form-prompt)'
  )

  test.beforeEach(async ({ app }) => {
    const seedResp = await apiRequest(app, 'get', `/form_prompts/${SEED.pendingId}`)
    const hasSeed = seedResp.ok()
    if (!hasSeed) seedGuard.markUnavailable()
    expect(
      hasSeed,
      'Form step execution seed required (see syntara-mock-api formPrompts / exec-form-prompt)'
    ).toBeTruthy()
  })

  async function openSeedPanel(app: Page): Promise<void> {
    await openExecutionFormPromptDeepLink(app, SEED.executionId, SEED.pendingId, {
      expectedMessage: SEED.pendingMessage,
    })
    await expect(app.getByRole('textbox', { name: 'Reason' })).toBeVisible({ timeout: 15_000 })
  }

  test('UI-13: deep-link opens the form step panel with summary and fields', async ({ app }) => {
    await openSeedPanel(app)

    await expect(app.getByText('Prompt step', { exact: true })).toBeVisible()
    await expect(app.getByText(SEED.pendingMessage)).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Reason' })).toBeVisible()
    await expect(app.getByRole('button', { name: SEED.customSubmitLabel })).toBeVisible()
  })

  test('UI-4: shows validation error when submitting without required fields', async ({ app }) => {
    await openSeedPanel(app)

    await app.getByRole('button', { name: SEED.customSubmitLabel }).click()
    await expect(app.getByText('This field is required')).toBeVisible({ timeout: 10_000 })
    await expect(pfWidget(app, 'Alert').filter({ hasText: 'Form submitted' })).not.toBeVisible()
  })

  test('UI-13: activity table row opens the waiting form step panel', async ({ app }) => {
    await app.goto(toAppUrl(`/executions/${SEED.executionId}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    const activityTable = app.getByRole('grid', { name: 'Activity states' })
    await expect(activityTable).toBeVisible({ timeout: 15_000 })

    await activityTable.getByRole('row').filter({ hasText: SEED.pendingName }).click()

    await waitForFormPromptPanel(app)
    await expect(app.getByText(SEED.pendingMessage)).toBeVisible()
  })

  test('UI-13: Respond to prompt toolbar action opens the form step panel', async ({ app }) => {
    await app.goto(toAppUrl(`/executions/${SEED.executionId}?history=closed`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    const panelHeading = app.getByRole('heading', { name: 'Respond to prompt' })
    const respondButton = app.getByRole('button', { name: 'Respond to prompt' })

    await expect(async () => {
      if (await panelHeading.isVisible().catch(() => false)) {
        await app.getByRole('button', { name: 'Close form prompt panel' }).click()
        await expect(panelHeading).not.toBeVisible({ timeout: 10_000 })
      }
      await clickWhenEnabled(respondButton, { timeout: 10_000 })
      await waitForFormPromptPanel(app)
      await expect(app.getByText(SEED.pendingMessage)).toBeVisible()
    }).toPass({ timeout: 45_000, intervals: [2_000] })
  })

  test('closes the form step panel with the close control', async ({ app }) => {
    await openSeedPanel(app)

    await app.getByRole('button', { name: 'Close form prompt panel' }).click()
    await expect(app.getByRole('heading', { name: 'Respond to prompt' })).not.toBeVisible({ timeout: 10_000 })
  })

  test('navigates between form steps with previous and next', async ({ app }) => {
    const panelHeading = app.getByRole('heading', { name: 'Respond to prompt' })
    const prevButton = app.getByRole('button', { name: 'Previous prompt' })
    const nextButton = app.getByRole('button', { name: 'Next prompt' })

    const deepLink = toAppUrl(`/executions/${SEED.executionId}?form_prompt=${SEED.pendingId}&history=closed`)

    await expect(async () => {
      await app.goto(deepLink)
      await waitForFormPromptPanel(app, { expectedMessage: SEED.pendingMessage })

      const counter = panelHeading.getByText(/\d+ of \d+/)
      await expect(counter).toHaveText('1 of 2', { timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })

      await expect(prevButton).toBeDisabled({ timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })

      await clickWhenEnabled(nextButton, { timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })
      await expect(counter).toHaveText('2 of 2', { timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })
      await expect(app.getByText(SEED.pendingMessage)).not.toBeVisible({ timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })

      await clickWhenEnabled(prevButton, { timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })
      await expect(counter).toHaveText('1 of 2', { timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })
      await expect(app.getByText(SEED.pendingMessage)).toBeVisible({ timeout: FORM_PROMPT_NAV_STEP_TIMEOUT })
    }).toPass({ timeout: 60_000, intervals: [3_000] })
  })

  test('UI-14: displays resolved dynamic dropdown options in the form step panel', async ({ app }) => {
    await openExecutionFormPromptDeepLink(app, SEED.executionId, SEED.dynamicPendingId, {
      expectedMessage: SEED.dynamicPendingMessage,
    })

    const environmentField = app.getByRole('combobox', { name: 'Environment' })
    await expect(environmentField).toBeVisible({ timeout: 15_000 })
    await environmentField.click()
    await expect(app.getByRole('option', { name: 'Development' })).toBeVisible()
    await expect(app.getByRole('option', { name: 'Production' })).toBeVisible()
  })

  test('UI-16: shows expired state when the response window has ended', async ({ app }) => {
    const expiredAt = new Date(Date.now() - 60_000).toISOString()

    await app.route(`**/form_prompts/${SEED.pendingId}`, async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      const response = await route.fetch()
      const body = (await response.json()) as Record<string, unknown>
      await route.fulfill({
        response,
        json: {
          ...body,
          status: 'pending',
          timeout_at: expiredAt,
        },
      })
    })

    await openExecutionFormPromptDeepLink(app, SEED.executionId, SEED.pendingId, {
      expectedMessage: SEED.pendingMessage,
    })

    await expect(app.getByText(/no longer accepting responses/i)).toBeVisible({ timeout: 15_000 })
    await expect(app.getByRole('button', { name: SEED.customSubmitLabel })).not.toBeVisible()
  })
})

test.describe('Execution detail — Form step side panel (viewer)', { tag: '@pr-check' }, () => {
  test('UI-10: viewer without submit permission sees a read-only form step panel', async ({ viewerApp }) => {
    await openExecutionFormPromptDeepLink(viewerApp, SEED.executionId, SEED.pendingId, {
      expectedMessage: SEED.pendingMessage,
    })
    await expect(viewerApp.getByRole('textbox', { name: 'Reason' })).toBeDisabled({ timeout: 20_000 })
    await expect(viewerApp.getByRole('button', { name: 'Submit response' })).not.toBeVisible()
  })
})

test.describe('Execution detail — Form step submit (API-created)', { tag: '@pr-check' }, () => {
  test('UI-7 and UI-13: submits a pending form step and shows customized success feedback', async ({ app }) => {
    const created = await createPendingFormPromptLight(app, 'e2e-panel-submit')

    try {
      await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)

      await app.getByRole('textbox', { name: 'Answer' }).fill('E2E panel submit')
      await app.getByRole('button', { name: 'Submit response' }).click()

      const successAlert = pfWidget(app, 'Alert').filter({ hasText: 'Form submitted' })
      await expect(successAlert).toBeVisible({ timeout: 15_000 })
      await expect(successAlert).toContainText(SEED.customSuccessMessage)
      await expect(app.getByRole('heading', { name: 'Respond to prompt' })).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflowViaApi(app, created.workflowId)
    }
  })

  test('shows an error alert when the submit API fails', async ({ app }) => {
    const created = await createPendingFormPromptLight(app, 'e2e-panel-submit-fail')

    try {
      await app.route('**/form_prompts/*/submit', async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            type: 'https://api.example.com/errors/internal',
            title: 'Internal Server Error',
            detail: 'Simulated submit failure for E2E',
            code: 'INTERNAL_ERROR',
            retryable: true,
          }),
        })
      })

      await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)

      await app.getByRole('textbox', { name: 'Answer' }).fill('E2E submit failure probe')
      await app.getByRole('button', { name: 'Submit response' }).click()

      await expect(pfWidget(app, 'Alert').filter({ hasText: 'Failed to submit form' })).toBeVisible({
        timeout: 15_000,
      })
      await expect(pfWidget(app, 'Alert').filter({ hasText: 'Form submitted' })).not.toBeVisible()
      await expect(app.getByRole('button', { name: 'Submit response' })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, created.workflowId)
    }
  })

  test('submitted form step shows read-only response data in the panel', async ({ app }) => {
    const created = await createPendingFormPromptLight(app, 'e2e-panel-readonly')
    const answer = 'Read-only E2E response'

    try {
      const submitResp = await apiRequest(app, 'post', `/form_prompts/${created.formPromptId}/submit`, {
        data: { response_data: { answer } },
      })
      expect(submitResp.ok(), `submit returned ${submitResp.status()}`).toBeTruthy()

      await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)

      await expect(app.getByText('Submitted response', { exact: true })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByText(answer)).toBeVisible()
      await expect(app.getByRole('button', { name: 'Submit response' })).not.toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, created.workflowId)
    }
  })
})
