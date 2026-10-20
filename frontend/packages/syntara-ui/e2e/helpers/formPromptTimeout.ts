import type { Route } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import { deleteWorkflowViaApi } from '../utils/api'
import { apiUrl } from '../utils/api-core'

import {
  MOCK_FORM_RESPONSE_SEED,
  SIDE_PANEL_REASON_FORM_DEFINITION,
  createPendingFormStepWorkflow,
} from './formResponses'

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

async function readJsonObject(response: { json: () => Promise<unknown> }): Promise<Record<string, unknown>> {
  try {
    const body = await response.json()
    return typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

async function fulfillJsonRoute(route: Route, transform: (body: Record<string, unknown>) => Record<string, unknown>) {
  const response = await route.fetch()
  const body = await readJsonObject(response)
  await route.fulfill({
    status: response.ok() ? response.status() : 200,
    headers: { ...response.headers(), 'content-type': 'application/json' },
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
      id: promptId,
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
  {
    executionId,
    promptId,
    formPromptNodeId = 'collect_input',
  }: { executionId: string; promptId: string; fallbackStepName: string; formPromptNodeId?: string }
): Promise<void> {
  await app.route(`**/api/v1/executions/${executionId}**`, async (route) => {
    if (!isExecutionDetailGet(route)) {
      await route.continue()
      return
    }
    await fulfillJsonRoute(route, (body) => {
      const execution = body as ExecutionDetailBody
      const activities: ActivityRecord[] = [...(execution.activities ?? [])]
      const collectIndex = activities.findIndex((row) => row.activity_id === formPromptNodeId)
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
          activity_id: formPromptNodeId,
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
      id: promptId,
      status: 'expired',
      timeout_at: EXPIRED_TIMEOUT_AT,
    }))
  })
}

export type TimeoutWaitingScenario = {
  executionId: string
  promptId: string
  activityLabel: string
  workflowId?: string
}

export type TimeoutFallbackScenario = TimeoutWaitingScenario & {
  fallbackStepName: string
}

/** Waiting form step with a short running-long threshold (mock seed or API-created execution). */
export async function ensureTimeoutWaitingScenario(app: Page): Promise<TimeoutWaitingScenario> {
  const { waitingExecutionId, waitingPromptId, waitingActivityLabel } = MOCK_FORM_PROMPT_TIMEOUT_SEED
  if (await hasMockExecutionSeed(app, waitingExecutionId)) {
    return {
      executionId: waitingExecutionId,
      promptId: waitingPromptId,
      activityLabel: waitingActivityLabel,
    }
  }

  if (!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
    throw new Error('Temporal worker required for form prompt timeout E2E on the real backend')
  }

  const created = await createPendingFormStepWorkflow(app, {
    namePrefix: 'e2e-timeout-waiting',
    formPromptNodeId: 'collect_input',
    formPromptNodeSettings: { timeout: 1 },
    parameters: {
      message: MOCK_FORM_RESPONSE_SEED.pendingMessage,
      form_definition: SIDE_PANEL_REASON_FORM_DEFINITION,
      submit_label: MOCK_FORM_RESPONSE_SEED.customSubmitLabel,
      responder_users: [],
      responder_groups: [],
    },
  })

  return {
    executionId: created.executionId,
    promptId: created.formPromptId,
    activityLabel: created.promptName,
    workflowId: created.workflowId,
  }
}

export async function ensureTimeoutExpiredFailScenario(app: Page): Promise<TimeoutWaitingScenario> {
  const { expiredFailExecutionId, expiredFailPromptId, waitingActivityLabel } = MOCK_FORM_PROMPT_TIMEOUT_SEED
  if (await hasMockExecutionSeed(app, expiredFailExecutionId)) {
    return {
      executionId: expiredFailExecutionId,
      promptId: expiredFailPromptId,
      activityLabel: waitingActivityLabel,
    }
  }

  const waiting = await ensureTimeoutWaitingScenario(app)
  await routeExpiredFailScenario(app, { executionId: waiting.executionId, promptId: waiting.promptId })
  return waiting
}

export async function ensureTimeoutFallbackScenario(app: Page): Promise<TimeoutFallbackScenario> {
  const { fallbackContinueExecutionId, fallbackExpiredPromptId, waitingActivityLabel, fallbackStepName } =
    MOCK_FORM_PROMPT_TIMEOUT_SEED

  if (await hasMockExecutionSeed(app, fallbackContinueExecutionId)) {
    return {
      executionId: fallbackContinueExecutionId,
      promptId: fallbackExpiredPromptId,
      activityLabel: waitingActivityLabel,
      fallbackStepName,
    }
  }

  if (!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
    throw new Error('Temporal worker required for form prompt timeout E2E on the real backend')
  }

  const fallbackNodeName = fallbackStepName
  const created = await createPendingFormStepWorkflow(app, {
    namePrefix: 'e2e-timeout-fallback',
    formPromptNodeId: 'collect_input',
    parameters: {
      message: MOCK_FORM_RESPONSE_SEED.pendingMessage,
      form_definition: SIDE_PANEL_REASON_FORM_DEFINITION,
      submit_label: MOCK_FORM_RESPONSE_SEED.customSubmitLabel,
      fallback_decision: 'fallback',
      responder_users: [],
      responder_groups: [],
    },
    trailingNodes: [
      {
        id: 'script_submitted',
        type: 'script',
        name: 'Submitted branch placeholder',
        parameters: { language: 'python', code: 'print("submitted")' },
      },
      {
        id: 'continue_with_defaults',
        type: 'script',
        name: fallbackNodeName,
        parameters: { language: 'python', code: 'print("fallback")' },
      },
    ],
    trailingEdges: [
      { from: 'collect_input', to: 'script_submitted', from_port: 'submitted' },
      { from: 'collect_input', to: 'continue_with_defaults', from_port: 'fallback' },
    ],
  })

  await routeFallbackContinueScenario(app, {
    executionId: created.executionId,
    promptId: created.formPromptId,
    fallbackStepName: fallbackNodeName,
  })

  return {
    executionId: created.executionId,
    promptId: created.formPromptId,
    activityLabel: created.promptName,
    fallbackStepName: fallbackNodeName,
    workflowId: created.workflowId,
  }
}

export async function disposeTimeoutScenario(app: Page, scenario: { workflowId?: string }): Promise<void> {
  if (scenario.workflowId) {
    await deleteWorkflowViaApi(app, scenario.workflowId)
  }
}

function executionDetailReadyTimeoutMs(): number {
  return process.env['SYNTARA_E2E_SKIP_WEB_SERVER'] ? 45_000 : 15_000
}

export async function waitForExecutionDetailReady(app: Page): Promise<void> {
  const timeout = executionDetailReadyTimeoutMs()
  await expect(app.getByRole('heading', { name: 'Loading execution' })).toHaveCount(0, { timeout })
  await expect(app.getByRole('heading', { name: 'Access denied', level: 2 })).toHaveCount(0, { timeout: 5_000 })
  await expect(app.getByRole('grid', { name: 'Activity states' })).toBeVisible({ timeout })
}

export async function openExecutionDetail(app: Page, executionId: string): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}`))
  await waitForExecutionDetailReady(app)
}

export async function openFormPromptRespondPanel(app: Page, executionId: string, formPromptId: string): Promise<void> {
  const timeout = executionDetailReadyTimeoutMs()
  await app.goto(toAppUrl(`/executions/${executionId}?form_prompt=${formPromptId}&history=closed`))
  await expect(app.getByRole('heading', { name: 'Loading execution' })).toHaveCount(0, { timeout })
  await expect(app.getByRole('heading', { name: /Respond to prompt/ })).toBeVisible({ timeout })
  await expect(app.getByRole('grid', { name: 'Activity states' })).toBeVisible({ timeout })
}
