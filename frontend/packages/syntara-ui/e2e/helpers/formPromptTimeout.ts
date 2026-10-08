import type { Route } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import { apiUrl } from '../utils/api-core'

/**
 * Mock API seeds for form step timeout and fallback continuation scenarios (text fields only; no file upload).
 * See syntara-mock-api: executions.ts, formPrompts.ts, activityExecutions.ts, executionDetails.ts.
 */
export const MOCK_FORM_PROMPT_TIMEOUT_SEED = {
  waitingExecutionId: 'exec-form-prompt',
  waitingPromptId: 'fp-exec-form-prompt-1',
  waitingActivityLabel: 'Collect operator input',
  expiredFailExecutionId: 'exec-form-prompt-timeout-fail',
  expiredFailPromptId: 'fp-exec-form-prompt-timeout-fail',
  fallbackContinueExecutionId: 'exec-form-prompt-fallback-continue',
  /** Expired collect_input prompt on `fallbackContinueExecutionId` (form step panel deep-links). */
  fallbackExpiredPromptId: 'fp-exec-form-prompt-fallback-expired',
  fallbackStepName: 'Continue with defaults step',
} as const

/** True when the mock API process includes the timeout/fallback execution seeds (fresh CI mock). */
export async function hasMockExecutionSeed(app: Page, executionId: string): Promise<boolean> {
  const response = await app.request.get(apiUrl(`/executions/${executionId}`))
  return response.ok()
}

const EXPIRED_TIMEOUT_AT = '2026-06-15T08:00:00.000Z'
const FAILED_COMPLETED_AT = '2026-06-15T09:00:00.000Z'

type ActivityRecord = {
  activity_id?: string
  status?: string
  started_at?: string | null
  completed_at?: string | null
  error_details?: string | null
}

type ExecutionDetailBody = {
  activities?: ActivityRecord[]
  status?: string
  completed_at?: string | null
  current_activities?: Array<{
    activity_name: string
    temporal_activity_id: string
    iteration: number | null
  }>
  workflow_definition?: { nodes: Array<Record<string, unknown>> }
}

function isExecutionDetailGet(route: Route): boolean {
  if (route.request().method() !== 'GET') {
    return false
  }
  const url = new URL(route.request().url())
  return /\/api\/v1\/executions\/[^/]+$/.test(url.pathname)
}

async function fulfillJsonRoute(route: Route, transform: (body: Record<string, unknown>) => Record<string, unknown>) {
  const response = await route.fetch()
  const body = (await response.json()) as Record<string, unknown>
  await route.fulfill({
    status: response.status(),
    headers: response.headers(),
    body: JSON.stringify(transform(body)),
  })
}

/**
 * Patches execution + form step APIs for a failed run with an expired response window.
 * Optional when the mock API was started before timeout-fail seeds existed (reuseExistingServer locally).
 */
export async function routeExpiredFailScenario(
  app: Page,
  { executionId, promptId }: { executionId: string; promptId: string }
): Promise<void> {
  await app.route(`**/api/v1/executions/${executionId}**`, async (route) => {
    if (!isExecutionDetailGet(route)) {
      await route.continue()
      return
    }
    await fulfillJsonRoute(route, (body) => ({
      ...body,
      status: 'failed',
      completed_at: FAILED_COMPLETED_AT,
      current_activities: [],
    }))
  })

  await app.route(`**/api/v1/form_prompts/${promptId}`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    await fulfillJsonRoute(route, (body) => ({
      ...body,
      status: 'expired',
      timeout_at: EXPIRED_TIMEOUT_AT,
    }))
  })
}

/**
 * Patches execution + form step APIs for a run that continued on the fallback branch.
 * Optional when the mock API was started before fallback-continue seeds existed (reuseExistingServer locally).
 */
export async function routeFallbackContinueScenario(
  app: Page,
  { executionId, promptId, fallbackStepName }: { executionId: string; promptId: string; fallbackStepName: string }
): Promise<void> {
  await app.route(`**/api/v1/executions/${executionId}**`, async (route) => {
    if (!isExecutionDetailGet(route)) {
      await route.continue()
      return
    }
    await fulfillJsonRoute(route, (body) => {
      const execution = body as ExecutionDetailBody
      const activities: ActivityRecord[] = [...(execution.activities ?? [])]
      const collectIndex = activities.findIndex((row) => row.activity_id === 'collect_input')
      const fallbackIndex = activities.findIndex((row) => row.activity_id === 'continue_with_defaults')

      if (collectIndex >= 0) {
        activities[collectIndex] = {
          ...activities[collectIndex],
          status: 'failed',
          completed_at: FAILED_COMPLETED_AT,
          error_details: 'Form step response window expired',
        }
      } else {
        activities.push({
          activity_id: 'collect_input',
          status: 'failed',
          started_at: '2026-06-15T07:50:00.000Z',
          completed_at: FAILED_COMPLETED_AT,
          error_details: 'Form step response window expired',
        })
      }

      if (fallbackIndex >= 0) {
        activities[fallbackIndex] = {
          ...activities[fallbackIndex],
          status: 'running',
          completed_at: null,
        }
      } else {
        activities.push({
          activity_id: 'continue_with_defaults',
          status: 'running',
          started_at: '2026-06-15T09:00:00.000Z',
          completed_at: null,
        })
      }

      return {
        ...body,
        status: 'running',
        completed_at: null,
        current_activities: [
          {
            activity_name: 'continue_with_defaults',
            temporal_activity_id: 'continue_with_defaults-activity',
            iteration: null,
          },
        ],
        workflow_definition: {
          nodes: [
            { id: 'collect_input', type: 'form_prompt', name: 'Collect operator input' },
            { id: 'continue_with_defaults', type: 'script', name: fallbackStepName },
          ],
        },
        activities,
      }
    })
  })

  await app.route(`**/api/v1/form_prompts/${promptId}`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    await fulfillJsonRoute(route, (body) => ({
      ...body,
      status: 'expired',
      timeout_at: EXPIRED_TIMEOUT_AT,
    }))
  })
}

export async function waitForExecutionDetailReady(app: Page): Promise<void> {
  await expect(app.getByRole('heading', { name: 'Loading execution' })).toHaveCount(0, { timeout: 15_000 })
  await expect(app.getByRole('grid', { name: 'Activity states' })).toBeVisible({ timeout: 15_000 })
}

export async function openExecutionDetail(app: Page, executionId: string): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}`))
  await waitForExecutionDetailReady(app)
}

export async function openFormPromptRespondPanel(app: Page, executionId: string, formPromptId: string): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}?form_prompt=${formPromptId}&history=closed`))
  await waitForExecutionDetailReady(app)
  await expect(app.getByRole('heading', { name: /Respond to prompt/ })).toBeVisible({ timeout: 15_000 })
}
