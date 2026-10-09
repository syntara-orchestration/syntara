/**
 * E2E: Form step timeout, waiting indicators, and fallback continuation.
 *
 * Covered in this file (forms interactive-prompt Playwright plan):
 * - UI-16 (fail path): expired response window — panel closed, no submit, execution Failed (test 1);
 *   running-long / deadline warning while still waiting (test 2).
 * - UI-17 (continue with defaults): after expiry, execution stays Running on the fallback step (test 4).
 * - UI-13 follow-ups: “Waiting for input” on the activity table + elapsed on the canvas badge (test 3).
 */

import { test, expect } from '../fixtures'
import {
  hasMockExecutionSeed,
  MOCK_FORM_PROMPT_TIMEOUT_SEED,
  openExecutionDetail,
  openFormPromptRespondPanel,
  routeExpiredFailScenario,
  routeFallbackContinueScenario,
} from '../helpers/formPromptTimeout'
import { apiUrl } from '../utils/api-core'

test.describe('Form step timeout and waiting indicators', { tag: '@pr-check' }, () => {
  test.afterEach(async ({ app }) => {
    await app.unrouteAll()
  })

  test('blocks submit when the response window has ended on a failed run', async ({ app }) => {
    const { expiredFailExecutionId, expiredFailPromptId, waitingExecutionId, waitingPromptId } =
      MOCK_FORM_PROMPT_TIMEOUT_SEED

    const hasDedicatedSeed = await hasMockExecutionSeed(app, expiredFailExecutionId)
    const executionId = hasDedicatedSeed ? expiredFailExecutionId : waitingExecutionId
    const promptId = hasDedicatedSeed ? expiredFailPromptId : waitingPromptId
    if (!hasDedicatedSeed) {
      await routeExpiredFailScenario(app, { executionId, promptId })
    }

    await openFormPromptRespondPanel(app, executionId, promptId)

    await expect(app.getByText('Form prompt closed')).toBeVisible()
    await expect(app.getByText(/expired/i)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit response' })).toHaveCount(0)
    await expect(app.getByLabel('Reason')).toHaveCount(0)

    await expect(app.getByTestId('execution-status-badge').getByText('Failed')).toBeVisible()
  })

  test('shows waiting elapsed time and running long warning while the form step panel is open', async ({ app }) => {
    const { waitingExecutionId, waitingPromptId } = MOCK_FORM_PROMPT_TIMEOUT_SEED

    await openFormPromptRespondPanel(app, waitingExecutionId, waitingPromptId)

    await expect(app.getByText('Running long')).toBeVisible()
    await expect(app.getByText('This prompt is approaching its response deadline.')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Submit response' })).toBeVisible()
  })

  test('shows waiting status on the activity table and elapsed time on the canvas badge', async ({ app }) => {
    const { waitingExecutionId, waitingActivityLabel } = MOCK_FORM_PROMPT_TIMEOUT_SEED

    await openExecutionDetail(app, waitingExecutionId)

    const activityTable = app.getByRole('grid', { name: 'Activity states' })
    const formRow = activityTable.getByRole('row').filter({ hasText: waitingActivityLabel })
    await expect(formRow).toBeVisible()
    await expect(formRow.getByText('Waiting for input')).toBeVisible()

    await expect(app.getByRole('img', { name: /Waiting for input, elapsed/ })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('shows the workflow running on the fallback branch after the response window expired', async ({ app }) => {
    const {
      fallbackContinueExecutionId,
      fallbackExpiredPromptId,
      fallbackStepName,
      waitingActivityLabel,
      waitingExecutionId,
      waitingPromptId,
    } = MOCK_FORM_PROMPT_TIMEOUT_SEED

    const hasDedicatedSeed = await hasMockExecutionSeed(app, fallbackContinueExecutionId)
    const executionId = hasDedicatedSeed ? fallbackContinueExecutionId : waitingExecutionId
    const promptId = hasDedicatedSeed ? fallbackExpiredPromptId : waitingPromptId
    if (!hasDedicatedSeed) {
      await routeFallbackContinueScenario(app, {
        executionId,
        promptId: waitingPromptId,
        fallbackStepName,
      })
    }

    await openExecutionDetail(app, executionId)
    await expect(app.getByTestId('execution-status-badge').getByText('Running')).toBeVisible()

    if (hasDedicatedSeed) {
      const promptResponse = await app.request.get(apiUrl(`/form_prompts/${promptId}`))
      expect(promptResponse.ok()).toBe(true)
      const promptBody = (await promptResponse.json()) as { status?: string }
      expect(promptBody.status).toBe('expired')
    }

    const activityTable = app.getByRole('grid', { name: 'Activity states' })
    const collectRow = activityTable.getByRole('row').filter({ hasText: waitingActivityLabel })
    await expect(collectRow).toBeVisible()
    await expect(collectRow.getByText('Failed')).toBeVisible()

    const fallbackRow = activityTable.getByRole('row').filter({ hasText: fallbackStepName })
    await expect(fallbackRow).toBeVisible()
    await expect(fallbackRow.getByText('Running')).toBeVisible()
  })
})
