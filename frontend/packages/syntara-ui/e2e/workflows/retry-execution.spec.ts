/**
 * E2E Tests: Retry Execution
 * Jira: AAP-82023
 *
 * Objective: Verify the retry execution flow from all three entry points:
 * 1. Execution detail page header button
 * 2. Workflow Runs table kebab menu
 * 3. Builder run history panel kebab menu
 *
 * Requires a real backend with Temporal — the workflow must complete before
 * retry actions become available. Uses a short wait node (not script) so the
 * fixture does not depend on Execution Plane cold-start dispatch.
 */

import { test, expect, toAppUrl, type Page } from '../fixtures'
import { buildUniqueName, openBuilderById } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  ensureProject,
  getAuthToken,
  pollExecutionStatus,
} from '../utils/api'

const TERMINAL_STATUSES = ['completed', 'completed_with_errors', 'failed', 'cancelled']

/** Podman Compose E2E and merge queue runs need more headroom for Temporal to finish under load. */
const TERMINAL_POLL_TIMEOUT_MS = process.env.CI ? 180_000 : 90_000

let workflowId: string | null = null
let completedExecutionId: string | null = null
const retriedExecutionIds: string[] = []

test.beforeAll(async ({ browser }) => {
  // Hook default matches test timeout (60s); allow the full terminal poll budget.
  test.setTimeout(TERMINAL_POLL_TIMEOUT_MS + 30_000)

  const page = await browser.newPage()
  try {
    const project = await ensureProject(page)
    if (!project) throw new Error('Could not ensure project for retry-execution tests')
    const token = await getAuthToken(page)
    if (!token) throw new Error('Could not obtain auth token')

    const name = buildUniqueName('e2e-retry')
    ;({ id: workflowId } = await createWorkflowViaApi({
      app: page,
      name,
      triggers: [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
      nodes: [
        {
          id: 'quick_wait',
          type: 'wait',
          name: 'Quick Wait',
          parameters: { duration: 1 },
        },
      ],
      edges: [{ from: 'trigger_manual', to: 'quick_wait' }],
    }))

    const runResp = await apiRequest(page, 'post', '/executions', {
      token,
      data: { workflow_id: workflowId, trigger_node_id: 'trigger_manual' },
    })
    if (!runResp.ok()) {
      throw new Error(`Failed to start retry fixture execution: ${runResp.status()} ${await runResp.text()}`)
    }
    const body = (await runResp.json()) as { id: string }
    completedExecutionId = body.id
    await pollExecutionStatus(page, completedExecutionId, TERMINAL_STATUSES, {
      token,
      timeout: TERMINAL_POLL_TIMEOUT_MS,
    })
  } finally {
    await page.close()
  }
})

async function deleteExecution(page: Page, executionId: string): Promise<void> {
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
    if (completedExecutionId) await deleteExecution(page, completedExecutionId)
    for (const id of retriedExecutionIds) {
      await deleteExecution(page, id)
    }
    if (workflowId) await deleteWorkflowViaApi(page, workflowId)
  } finally {
    await page.close()
  }
})

test.describe('Retry Execution', () => {
  test.describe.configure({ mode: 'serial' })

  test.describe('Execution detail page', () => {
    test('retry button is visible for a completed execution', async ({ app }) => {
      expect(completedExecutionId, 'completedExecutionId must be set by beforeAll').not.toBeNull()

      await app.goto(toAppUrl(`/executions/${completedExecutionId!}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

      await expect(app.getByRole('button', { name: 'Retry run' })).toBeVisible()
    })

    test('clicking retry opens confirmation dialog and cancel closes it', async ({ app }) => {
      await app.goto(toAppUrl(`/executions/${completedExecutionId!}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

      await app.getByRole('button', { name: 'Retry run' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Retry run?')).toBeVisible()
      await expect(dialog.getByText(/You are about to retry this workflow run/)).toBeVisible()

      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('confirming retry navigates to new execution @pr-check', async ({ app }) => {
      await app.goto(toAppUrl(`/executions/${completedExecutionId!}`))
      await expect(app.getByRole('heading', { level: 1 })).toBeVisible()

      await app.getByRole('button', { name: 'Retry run' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: 'Retry run' }).click()

      await expect(app.getByText('Execution retry started')).toBeVisible({ timeout: 10_000 })

      // Should navigate to the new execution's detail page
      await expect(() => {
        const url = app.url()
        expect(url).toMatch(/\/executions\/[a-f0-9-]+$/)
        expect(url).not.toContain(completedExecutionId!)
      }).toPass({ timeout: 10_000, intervals: [1_000] })

      // Track the new execution ID for cleanup
      const newUrl = app.url()
      const match = newUrl.match(/\/executions\/([a-f0-9-]+)$/)
      if (match) retriedExecutionIds.push(match[1])
    })
  })

  test.describe('Workflow Runs table', () => {
    test('retry available in table kebab menu', async ({ app }) => {
      expect(completedExecutionId, 'completedExecutionId must be set by beforeAll').not.toBeNull()

      await app.goto(toAppUrl('/executions'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

      const row = app.getByRole('row').filter({ hasText: completedExecutionId! })
      await expect(row).toBeVisible({ timeout: 10_000 })

      const kebab = row.getByRole('button', { name: new RegExp('Actions for execution') })
      await kebab.click()

      await expect(app.getByText('Retry run')).toBeVisible()
    })
  })

  test.describe('Builder run history panel', () => {
    test('retry available in run history kebab menu', async ({ app }) => {
      expect(workflowId, 'workflowId must be set by beforeAll').not.toBeNull()

      await openBuilderById(app, workflowId!)
      await expect(app.getByText('Manual trigger')).toBeVisible({ timeout: 30_000 })

      // Open run history via the builder kebab menu → "Run history" item
      const workflowKebab = app.getByRole('button', { name: 'Workflow actions' })
      await expect(workflowKebab).toBeVisible()
      await workflowKebab.click()
      await app.getByText('Run history').click()

      // Wait for the run history panel to render
      await expect(app.getByRole('heading', { name: 'Run history', level: 2 })).toBeVisible({ timeout: 15_000 })

      // The kebab button only renders for retryable executions (terminal status,
      // non-test mode), so its presence proves retry is available. We don't click
      // through the dropdown here because the history panel's overflow:hidden clips
      // the Popper menu — the dropdown interaction is covered by earlier tests.
      const truncatedId = completedExecutionId!.slice(0, 8)
      await expect(
        app.getByRole('button', {
          name: `Actions for execution ${truncatedId}`,
          exact: true,
        })
      ).toBeVisible({ timeout: 30_000 })
    })
  })
})
