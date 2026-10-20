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
import { activityTableRowByActivityName } from '../helpers/formPromptPanel'
import {
  disposeTimeoutScenario,
  ensureTimeoutExpiredFailScenario,
  ensureTimeoutFallbackScenario,
  ensureTimeoutWaitingScenario,
  hasMockExecutionSeed,
  MOCK_FORM_PROMPT_TIMEOUT_SEED,
  openExecutionDetail,
  openFormPromptRespondPanel,
  waitForExecutionDetailReady,
} from '../helpers/formPromptTimeout'
import { pfWidget } from '../helpers/patternfly'
import { apiRequest } from '../utils/api'

test.describe('Form step timeout and waiting indicators', { tag: '@pr-check' }, () => {
  test.beforeEach(async ({ app }) => {
    const hasMock = await hasMockExecutionSeed(app, MOCK_FORM_PROMPT_TIMEOUT_SEED.waitingExecutionId)
    if (!hasMock && !process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
      test.skip(true, 'Temporal worker required for form prompt timeout E2E on the real backend (globalSetup probe)')
    }
  })

  test.afterEach(async ({ app }) => {
    await app.unrouteAll()
  })

  test('blocks submit when the response window has ended on a failed run', async ({ app }) => {
    const scenario = await ensureTimeoutExpiredFailScenario(app)

    try {
      await openFormPromptRespondPanel(app, scenario.executionId, scenario.promptId)

      const closedPanelAlert = pfWidget(app, 'Alert').filter({ hasText: 'Form prompt closed' })
      await expect(closedPanelAlert).toBeVisible()
      await expect(closedPanelAlert).toContainText('expired')
      await expect(app.getByRole('button', { name: 'Submit response' })).toHaveCount(0)
      await expect(app.getByLabel('Reason')).toHaveCount(0)

      await expect(app.getByTestId('execution-status-badge').getByText('Failed')).toBeVisible()
    } finally {
      await disposeTimeoutScenario(app, scenario)
    }
  })

  test('shows waiting elapsed time and running long warning while the form step panel is open', async ({ app }) => {
    const scenario = await ensureTimeoutWaitingScenario(app)

    try {
      await openFormPromptRespondPanel(app, scenario.executionId, scenario.promptId)

      await expect(app.getByText('Running long')).toBeVisible()
      await expect(app.getByText('This prompt is approaching its response deadline.')).toBeVisible()
      await expect(app.getByRole('button', { name: 'Submit response' })).toBeVisible()
    } finally {
      await disposeTimeoutScenario(app, scenario)
    }
  })

  test('shows waiting status on the activity table and elapsed time on the canvas badge', async ({ app }) => {
    const scenario = await ensureTimeoutWaitingScenario(app)

    try {
      await openExecutionDetail(app, scenario.executionId)

      const activityTable = app.getByRole('grid', { name: 'Activity states' })
      const formRow = activityTableRowByActivityName(activityTable, scenario.activityLabel)
      await expect(formRow).toBeVisible()
      await expect(formRow.getByText('Waiting for input')).toBeVisible()

      await expect(app.getByRole('img', { name: /Waiting for input, elapsed/ })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      await disposeTimeoutScenario(app, scenario)
    }
  })

  test('shows the workflow running on the fallback branch after the response window expired', async ({ app }) => {
    const scenario = await ensureTimeoutFallbackScenario(app)

    try {
      await openExecutionDetail(app, scenario.executionId)
      if (scenario.workflowId) {
        await app.reload()
        await waitForExecutionDetailReady(app)
      }

      const tableReadyTimeout = process.env['SYNTARA_E2E_SKIP_WEB_SERVER'] ? 45_000 : 15_000

      await expect(app.getByTestId('execution-status-badge').getByText('Running')).toBeVisible({
        timeout: tableReadyTimeout,
      })

      // apiRequest uses page.request which bypasses page.route() interception.
      // On compose (scenario.workflowId set), route patches fake the expired state
      // but direct API calls still hit the real backend where the prompt is pending.
      // Only check prompt status via direct API when using mock seeds.
      if (!scenario.workflowId) {
        await expect(async () => {
          const promptResponse = await apiRequest(app, 'get', `/form_prompts/${scenario.promptId}`)
          expect(promptResponse.ok()).toBe(true)
          const promptBody = (await promptResponse.json()) as { status?: string }
          expect(promptBody.status).toBe('expired')
        }).toPass({ timeout: tableReadyTimeout, intervals: [2_000] })
      }

      const activityTable = app.getByRole('grid', { name: 'Activity states' })
      const collectRow = activityTableRowByActivityName(activityTable, scenario.activityLabel)
      const fallbackRow = activityTableRowByActivityName(activityTable, scenario.fallbackStepName)

      await expect(collectRow).toBeVisible({ timeout: tableReadyTimeout })
      await expect(collectRow.getByText('Failed')).toBeVisible({ timeout: tableReadyTimeout })
      await expect(fallbackRow).toBeVisible({ timeout: tableReadyTimeout })
      await expect(fallbackRow.getByText('Running')).toBeVisible({ timeout: tableReadyTimeout })
    } finally {
      await disposeTimeoutScenario(app, scenario)
    }
  })
})
