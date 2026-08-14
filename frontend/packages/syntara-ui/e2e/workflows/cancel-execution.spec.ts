/**
 * E2E Tests: Cancel Execution
 *
 * Objective: Verify the cancel execution flow from the execution detail page.
 *
 * Critical paths:
 * - Cancel button visible for running executions
 * - Clicking cancel transitions execution to cancelled status
 * - Cancel button hidden for completed executions
 *
 * Requires a real backend with Temporal — the wait node keeps the execution
 * in "running" state long enough to interact with the cancel button.
 */

import { test, expect, toAppUrl, type Page } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { apiRequest, createWorkflowViaApi, deleteWorkflowViaApi, ensureProject, getAuthToken } from '../utils/api'

const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

async function pollExecutionStatus(
  page: Page,
  executionId: string,
  token: string,
  expectedStatuses: string[],
  timeout = 90_000
): Promise<void> {
  await expect(async () => {
    const resp = await apiRequest(page, 'get', `/executions/${executionId}`, { token })
    const exec = (await resp.json()) as { status: string }
    expect(expectedStatuses).toContain(exec.status)
  }).toPass({ timeout, intervals: [1_000] })
}

let sleepWorkflowId: string | null = null
let runningExecutionId: string | null = null
let echoWorkflowId: string | null = null
let completedExecutionId: string | null = null

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    const project = await ensureProject(page)
    if (!project) throw new Error('Could not ensure project for cancel-execution tests')
    const token = await getAuthToken(page)
    if (!token) throw new Error('Could not obtain auth token')

    const sleepName = buildUniqueName('e2e-cancel-sleep')
    ;({ id: sleepWorkflowId } = await createWorkflowViaApi(
      page,
      sleepName,
      [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
      [
        {
          id: 'long_wait',
          type: 'wait',
          name: 'Long Wait',
          parameters: { duration: 300 },
        },
      ],
      [{ from: 'trigger_manual', to: 'long_wait' }]
    ))

    const runResp = await apiRequest(page, 'post', '/executions', {
      token,
      data: { workflow_id: sleepWorkflowId, trigger_node_id: 'trigger_manual' },
    })
    if (runResp.ok()) {
      const body = (await runResp.json()) as { id: string }
      runningExecutionId = body.id
      await pollExecutionStatus(page, runningExecutionId, token, ['running'], 60_000)
    }

    const echoName = buildUniqueName('e2e-cancel-echo')
    ;({ id: echoWorkflowId } = await createWorkflowViaApi(
      page,
      echoName,
      [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
      [
        {
          id: 'quick_wait',
          type: 'wait',
          name: 'Quick Wait',
          parameters: { duration: 1 },
        },
      ],
      [{ from: 'trigger_manual', to: 'quick_wait' }]
    ))

    const echoRunResp = await apiRequest(page, 'post', '/executions', {
      token,
      data: { workflow_id: echoWorkflowId, trigger_node_id: 'trigger_manual' },
    })
    if (echoRunResp.ok()) {
      const body = (await echoRunResp.json()) as { id: string }
      completedExecutionId = body.id
      await pollExecutionStatus(page, completedExecutionId, token, TERMINAL_STATUSES)
    }
  } finally {
    await page.close()
  }
})

async function deleteExecution(page: Page, executionId: string | null): Promise<void> {
  if (!executionId) return
  try {
    const token = await getAuthToken(page)
    if (token) await apiRequest(page, 'delete', `/executions/${executionId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  try {
    await deleteExecution(page, runningExecutionId)
    await deleteExecution(page, completedExecutionId)
    if (sleepWorkflowId) await deleteWorkflowViaApi(page, sleepWorkflowId)
    if (echoWorkflowId) await deleteWorkflowViaApi(page, echoWorkflowId)
  } finally {
    await page.close()
  }
})

test.describe('Cancel Execution', () => {
  test.describe.configure({ mode: 'serial' })

  test('cancel button is visible for a running execution', async ({ app }) => {
    expect(runningExecutionId, 'runningExecutionId must be set by beforeAll').not.toBeNull()

    await app.goto(toAppUrl(`/executions/${runningExecutionId!}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

    await expect(app.getByRole('button', { name: 'Cancel run' })).toBeVisible()
  })

  test('clicking cancel transitions execution to cancelled @pr-check', async ({ app }, testInfo) => {
    testInfo.setTimeout(90_000)
    expect(runningExecutionId, 'runningExecutionId must be set by beforeAll').not.toBeNull()

    await app.goto(toAppUrl(`/executions/${runningExecutionId!}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

    const cancelButton = app.getByRole('button', { name: 'Cancel run' })
    await expect(cancelButton).toBeVisible()
    await cancelButton.click()

    await expect(app.getByText('Execution cancellation requested')).toBeVisible({ timeout: 10_000 })

    // Cancellation is async — poll by reloading until status updates
    await expect(async () => {
      await app.reload()
      await expect(app.getByText('Workflow was cancelled')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 60_000, intervals: [3_000, 5_000] })
  })

  test('cancel button is not visible for a completed execution', async ({ app }) => {
    expect(completedExecutionId, 'completedExecutionId must be set by beforeAll').not.toBeNull()

    await app.goto(toAppUrl(`/executions/${completedExecutionId!}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

    await expect(app.getByRole('button', { name: 'Cancel run' })).not.toBeVisible()
  })
})
