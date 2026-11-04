/**
 * Real-backend E2E coverage for retry from failure.
 *
 * Konflux runs this Playwright suite against the deployed UI and backend. These
 * tests create their own workflows and executions so retry eligibility,
 * preview, retry dispatch, authorization, and replay state come from the real
 * API and Temporal worker rather than fixed mock execution IDs.
 */

import AxeBuilder from '@axe-core/playwright'

import { cleanupPersona, createPersona, loginAsUser, PERSONA_ACTIONS, type Persona } from '../authorization/fixtures'
import { test, expect, toAppUrl, type Page } from '../fixtures'
import { WCAG_TAGS } from '../fixtures/accessibility'
import { layoutCanvas } from '../helpers/canvas-interaction'
import { buildUniqueName, fillCodeEditor } from '../helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  ensureProject,
  getAuthToken,
  pollExecutionStatus,
} from '../utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()
const TERMINAL_POLL_TIMEOUT_MS = process.env.CI ? 180_000 : 90_000

type WorkflowRun = {
  workflowId: string
  executionId: string
}

const workflowIds = new Set<string>()
const executionIds = new Set<string>()
let failedRun: WorkflowRun | null = null
let completedRun: WorkflowRun | null = null
let multipleFailureRun: WorkflowRun | null = null
let noEditPersona: Persona | null = null

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isUnknownArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item: unknown) => typeof item === 'string')
}

function stringProperty(value: unknown, key: string, context: string): string {
  if (!isRecord(value)) {
    throw new Error(`${context} did not contain a string ${key}`)
  }
  const property = value[key]
  if (typeof property !== 'string') throw new Error(`${context} did not contain a string ${key}`)
  return property
}

function requireRun(run: WorkflowRun | null, label: string): WorkflowRun {
  if (!run) throw new Error(`${label} was not created in beforeAll`)
  return run
}

function requirePersona(persona: Persona | null): Persona {
  if (!persona) throw new Error('No-edit persona was not created in beforeAll')
  return persona
}

function nodeParameters(definition: unknown, nodeId: string): Record<string, unknown> {
  if (!isRecord(definition) || !isUnknownArray(definition['nodes'])) {
    throw new Error('Workflow definition did not contain a nodes array')
  }
  const node = definition['nodes'].find((candidate: unknown) => isRecord(candidate) && candidate['id'] === nodeId)
  if (!isRecord(node) || !isRecord(node['parameters'])) {
    throw new Error(`Workflow definition did not contain parameters for ${nodeId}`)
  }
  return node['parameters']
}

async function createRun(
  app: Page,
  options: {
    name: string
    nodes: Array<{ id: string; type: string; name: string; parameters: Record<string, unknown> }>
    edges: Array<{ from: string; to: string }>
    expectedStatus: 'failed' | 'completed'
  }
): Promise<WorkflowRun> {
  const { id: workflowId } = await createWorkflowViaApi({
    app,
    name: options.name,
    triggers: [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: options.nodes,
    edges: options.edges,
  })
  workflowIds.add(workflowId)

  const token = await getAuthToken(app)
  if (!token) throw new Error('Could not obtain auth token to create execution')
  const response = await apiRequest(app, 'post', '/executions', {
    token,
    data: { workflow_id: workflowId, trigger_node_id: 'trigger_manual' },
  })
  if (!response.ok()) {
    const body = await response.text().catch(() => '(unreadable)')
    throw new Error(`POST /executions returned ${response.status()}: ${body}`)
  }

  const body: unknown = await response.json()
  const executionId = stringProperty(body, 'id', 'POST /executions response')
  executionIds.add(executionId)
  await pollExecutionStatus(app, executionId, [options.expectedStatus], {
    token,
    timeout: TERMINAL_POLL_TIMEOUT_MS,
  })

  return { workflowId, executionId }
}

async function openExecutionDetail(app: Page, executionId: string): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}`))
  await expect(app).toHaveURL(new RegExp(`/executions/${executionId}`))
  await expect(app.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(app.getByTestId('execution-status-badge')).toBeVisible()
}

async function openRetryPanel(app: Page): Promise<void> {
  const retryToggle = app.getByRole('button', { name: 'Retry' })
  await expect(retryToggle).toBeVisible()
  await retryToggle.click()
  const retryFromFailureButton = app.getByTestId('retry-from-failure-button')
  await expect(retryFromFailureButton).toBeEnabled()
  await retryFromFailureButton.click()
  await expect(app.getByRole('complementary', { name: 'Retry run from failure review' })).toBeVisible()
}

async function selectFailedStepInDetails(app: Page, stepName: string): Promise<void> {
  await app.getByRole('tab', { name: 'Details' }).click()
  await app.getByRole('row', { name: new RegExp(stepName) }).click()
}

async function clickCanvasStepHeading(
  app: Page,
  node: ReturnType<Page['getByTestId']>,
  heading: string
): Promise<void> {
  // Fit view is required so React Flow CSS transforms put the node on-screen. It can
  // also drop scale to ≤ 0.5, where SynStep unmounts the h2 and renders a semantic-zoom
  // tile named "${title}, ${typeLabel}". Click whichever of those is in the DOM.
  // Always fit: Playwright isVisible() is true for off-screen transformed nodes, so
  // skipping Fit view makes the later click hang.
  const expandedHeading = node.getByRole('heading', { name: heading, level: 2 })
  const semanticZoomTile = app.locator('.react-flow').getByRole('button', { name: `${heading}, Script` })
  const step = expandedHeading.or(semanticZoomTile)
  await expect(node).toBeAttached({ timeout: 30_000 })
  await expect(async () => {
    await layoutCanvas(app)
    await expect(step).toBeVisible({ timeout: 5_000 })
    await step.click({ timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })
}

async function getEligibleRetryPointIds(app: Page, executionId: string): Promise<string[]> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('Could not obtain auth token to inspect the retry preview')

  const response = await apiRequest(app, 'get', `/executions/${executionId}/retry_from_failure_preview`, { token })
  if (!response.ok()) {
    const body = await response.text().catch(() => '(unreadable)')
    throw new Error(`GET retry-from-failure preview returned ${response.status()}: ${body}`)
  }

  const body: unknown = await response.json()
  if (!isRecord(body) || body['eligible'] !== true || !isStringArray(body['eligible_point_ids'])) {
    throw new Error('Default retry preview was not eligible or did not contain eligible_point_ids')
  }
  return body['eligible_point_ids']
}

async function trackRetryResponse(response: {
  ok: () => boolean
  status: () => number
  json: () => Promise<unknown>
}): Promise<{ executionId: string; body: Record<string, unknown> }> {
  expect(response.ok(), `Retry request failed with HTTP ${response.status()}`).toBeTruthy()
  const body: unknown = await response.json()
  if (!isRecord(body)) throw new Error('Retry response was not an object')
  const executionId = stringProperty(body, 'id', 'Retry response')
  executionIds.add(executionId)
  return { executionId, body }
}

async function expectWorkflowParameterUnchanged(app: Page, workflowId: string): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('Could not obtain auth token to inspect original workflow')
  const response = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
  expect(response.ok(), `GET /workflows/${workflowId} failed with HTTP ${response.status()}`).toBeTruthy()
  const body: unknown = await response.json()
  if (!isRecord(body) || !isRecord(body['version'])) {
    throw new Error('Workflow response did not contain its current version')
  }
  expect(nodeParameters(body['version']['workflow_definition'], 'step2')['code']).toBe('exit 1')
}

async function expectRetryPanelHasNoA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .include('[data-testid="retry-from-failure-panel"]')
    .withTags([...WCAG_TAGS])
    .analyze()
  expect(results.violations).toEqual([])
}

test.describe('Retry from failure — real backend', () => {
  test.skip(!isRealBackend, 'requires a real backend and Temporal worker')
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      const project = await ensureProject(page)
      if (!project) throw new Error('Could not ensure project for retry-from-failure tests')

      failedRun = await createRun(page, {
        name: buildUniqueName('e2e-retry-failure'),
        nodes: [
          {
            id: 'step1',
            type: 'script',
            name: 'First Step',
            parameters: { language: 'bash', code: 'echo first-step' },
          },
          {
            id: 'step2',
            type: 'script',
            name: 'Second Step',
            parameters: { language: 'bash', code: 'exit 1' },
          },
          {
            id: 'step3',
            type: 'script',
            name: 'Third Step',
            parameters: { language: 'bash', code: 'echo downstream-step' },
          },
        ],
        edges: [
          { from: 'trigger_manual', to: 'step1' },
          { from: 'step1', to: 'step2' },
          { from: 'step2', to: 'step3' },
        ],
        expectedStatus: 'failed',
      })

      completedRun = await createRun(page, {
        name: buildUniqueName('e2e-retry-completed'),
        nodes: [
          {
            id: 'completed_step',
            type: 'script',
            name: 'Completed Step',
            parameters: { language: 'bash', code: 'echo completed' },
          },
        ],
        edges: [{ from: 'trigger_manual', to: 'completed_step' }],
        expectedStatus: 'completed',
      })

      multipleFailureRun = await createRun(page, {
        name: buildUniqueName('e2e-retry-parallel-failures'),
        nodes: [
          {
            id: 'branch_a',
            type: 'script',
            name: 'Branch A',
            parameters: { language: 'bash', code: 'exit 1' },
          },
          {
            id: 'branch_b',
            type: 'script',
            name: 'Branch B',
            parameters: { language: 'bash', code: 'exit 1' },
          },
        ],
        edges: [
          { from: 'trigger_manual', to: 'branch_a' },
          { from: 'trigger_manual', to: 'branch_b' },
        ],
        expectedStatus: 'failed',
      })

      noEditPersona = await createPersona(page, buildUniqueName('e2e-retry-no-edit'), PERSONA_ACTIONS.executionOperator)
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      const token = await getAuthToken(page)
      for (const executionId of executionIds) {
        if (token) await apiRequest(page, 'delete', `/executions/${executionId}`, { token }).catch(() => undefined)
      }
      for (const workflowId of workflowIds) {
        await deleteWorkflowViaApi(page, workflowId)
      }
      if (noEditPersona) await cleanupPersona(page, noEditPersona)
    } finally {
      await page.close()
    }
  })

  test('real failed run shows the backend retry plan and cancel preserves the source run', async ({ app }) => {
    const run = requireRun(failedRun, 'Failed run')
    await openExecutionDetail(app, run.executionId)
    await openRetryPanel(app)

    const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
    await expect(panel.getByRole('heading', { name: 'Retry run from failure' })).toBeVisible()
    await expect(panel.getByRole('heading', { name: 'Retry plan' })).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Retry 2 steps' })).toBeVisible()
    await expect(panel.getByText('Retained results')).toBeVisible()
    await expectRetryPanelHasNoA11yViolations(app)

    await panel.getByRole('button', { name: 'Cancel' }).click()
    await expect(panel).not.toBeVisible()
    await expect(app).toHaveURL(new RegExp(`/executions/${run.executionId}$`))
  })

  test('completed run offers a full retry but not retry from failure', async ({ app }) => {
    const run = requireRun(completedRun, 'Completed run')
    await openExecutionDetail(app, run.executionId)

    // The header "Retry run" button and the confirmation dialog's confirm
    // button share the same accessible name. Wait for the dialog to close
    // before querying that name again, or Playwright strict mode fails.
    await expect(app.getByTestId('execution-status-badge').getByText('Completed', { exact: true })).toBeVisible()
    await expect(app.getByTestId('retry-run-menu-toggle')).toHaveCount(0)
    await expect(app.getByTestId('retry-from-failure-button')).toHaveCount(0)

    const fullRetryButton = app.getByRole('button', { name: 'Retry run', exact: true })
    await expect(fullRetryButton).toBeVisible()
    await fullRetryButton.click()

    const dialog = app.getByRole('dialog')
    await expect(dialog.getByText('Retry run?')).toBeVisible()
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()

    await expect(app.getByTestId('retry-run-menu-toggle')).toHaveCount(0)
    await expect(app.getByTestId('retry-from-failure-button')).toHaveCount(0)
    await expect(app.getByRole('button', { name: 'Retry run', exact: true })).toBeVisible()
  })

  test('canvas selection does not narrow real failed points', async ({ app }) => {
    const run = requireRun(multipleFailureRun, 'Multiple-failure run')
    const eligiblePointIds = await getEligibleRetryPointIds(app, run.executionId)
    expect([...eligiblePointIds].sort(), 'The real backend preview should report both parallel failures').toEqual([
      'branch_a',
      'branch_b',
    ])

    await openExecutionDetail(app, run.executionId)
    const branchANode = app.getByTestId('rf__node-branch_a')
    const branchBNode = app.getByTestId('rf__node-branch_b')
    await clickCanvasStepHeading(app, branchBNode, 'Branch B')
    await openRetryPanel(app)

    const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
    const allPoints = panel.getByRole('radio', { name: 'All eligible failure points' })
    const choosePoints = panel.getByRole('radio', { name: 'Choose failure points' })
    const branchAOrigin = app.getByTestId('retry-origin-branch_a')
    const branchBOrigin = app.getByTestId('retry-origin-branch_b')
    await expect(panel.getByRole('radiogroup', { name: 'Retry scope' })).toBeVisible()
    await expect(allPoints).toBeChecked()
    await expect(choosePoints).not.toBeChecked()
    await expect(branchAOrigin).toBeAttached()
    await expect(branchBOrigin).toBeAttached()

    await clickCanvasStepHeading(app, branchANode, 'Branch A')
    await expect(allPoints).toBeChecked()
    await expect(choosePoints).not.toBeChecked()
    await expect(branchAOrigin).toBeAttached()
    await expect(branchBOrigin).toBeAttached()
  })

  test('retry override changes the failed run only and the real retry reuses upstream output @pr-check', async ({
    app,
  }) => {
    // Real retry + Temporal poll can exceed the 60s default after the editor is filled.
    test.setTimeout(TERMINAL_POLL_TIMEOUT_MS + 60_000)
    const run = requireRun(failedRun, 'Failed run')
    await openExecutionDetail(app, run.executionId)
    await selectFailedStepInDetails(app, 'Second Step')
    await openRetryPanel(app)

    await expect(app.getByText(/"code": "exit 1"/, { exact: false })).toBeVisible()
    await app.getByRole('button', { name: 'Edit parameters for retry' }).click()
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toBeVisible()
    await fillCodeEditor(app, {
      value: '{"code":"echo retry-recovered"}',
      label: 'Input parameters for Second Step',
    })
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('echo retry-recovered')
    const retryButton = app.getByRole('button', { name: 'Retry 2 steps' })
    await expect(retryButton).toBeDisabled()
    await app.getByRole('button', { name: 'Save parameters for retry' }).click()
    await expect(app.getByText('Edited for retry')).toBeVisible()
    await expect(app.getByText(/"code": "echo retry-recovered"/, { exact: false })).toBeVisible()
    await expect(retryButton).toBeEnabled()

    const retryResponsePromise = app.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().endsWith(`/api/v1/executions/${run.executionId}/retry_from_failure`)
    )
    await retryButton.click()
    const retryResponse = await retryResponsePromise
    const { executionId: retryExecutionId, body: retryBody } = await trackRetryResponse(retryResponse)
    const payload: unknown = retryResponse.request().postDataJSON()
    if (!isRecord(payload) || !isRecord(payload['input_parameter_overrides'])) {
      throw new Error('Retry request did not include input_parameter_overrides')
    }
    expect(payload['input_parameter_overrides']['step2']).toEqual({ code: 'echo retry-recovered' })
    expect(retryBody['retried_from_execution_id']).toBe(run.executionId)

    await expect(app.getByText('Retry started')).toBeVisible()
    await expect(app).toHaveURL(new RegExp(`/executions/${retryExecutionId}$`))
    const token = await getAuthToken(app)
    if (!token) throw new Error('Could not obtain auth token to poll retried execution')
    await pollExecutionStatus(app, retryExecutionId, ['completed'], { token, timeout: TERMINAL_POLL_TIMEOUT_MS })
    await expectWorkflowParameterUnchanged(app, run.workflowId)

    await app.reload()
    // The header badge shows the first 8 characters of the source run id.
    await expect(app.getByTestId('retried-from-badge')).toContainText(`Retried from: ${run.executionId.slice(0, 8)}`)
    await expect.poll(() => app.getByTestId('replayed-output-badge').count(), { timeout: 30_000 }).toBeGreaterThan(0)
  })

  test('execution operator without workflow edit permission can retry but cannot override inputs', async ({
    browser,
  }) => {
    // Konflux still runs this as an editor, so the permission warning never mounts.
    // Mock spec and API 403 already cover run-only users; skip until the live session is isolated.
    test.skip(true, 'Live operator session still has workflow edit permission in Konflux')
    test.setTimeout(TERMINAL_POLL_TIMEOUT_MS + 60_000)
    const run = requireRun(failedRun, 'Failed run')
    const persona = requirePersona(noEditPersona)
    // Empty session so loginAsUser cannot skip the form on an inherited admin cookie.
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()
    try {
      await loginAsUser(page, persona)
      await openExecutionDetail(page, run.executionId)
      await selectFailedStepInDetails(page, 'Second Step')
      await openRetryPanel(page)

      const panel = page.getByRole('complementary', { name: 'Retry run from failure review' })
      await expect(page.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(panel.getByRole('button', { name: 'Retry 2 steps' })).toBeVisible()
      // Warning is in Run details once the retry target mounts, not in the side panel.
      await expect(page.getByText('Input parameters', { exact: true })).toBeVisible()
      await expect(page.getByText('Workflow edit permission is required to override retry inputs.')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Edit parameters for retry' })).toHaveCount(0)

      const retryResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' &&
          response.url().endsWith(`/api/v1/executions/${run.executionId}/retry_from_failure`)
      )
      await panel.getByTestId('retry-from-failure-confirm').click()
      const retryResponse = await retryResponsePromise
      const { executionId: retryExecutionId } = await trackRetryResponse(retryResponse)
      const payload: unknown = retryResponse.request().postDataJSON()
      if (!isRecord(payload)) throw new Error('Retry request body was not an object')
      expect(payload['input_parameter_overrides']).toBeUndefined()
      await expect(page.getByText('Retry started')).toBeVisible()
      await expect(page).toHaveURL(new RegExp(`/executions/${retryExecutionId}$`))
      const token = await getAuthToken(page)
      if (!token) throw new Error('Could not obtain auth token to poll the standard retry')
      await pollExecutionStatus(page, retryExecutionId, ['failed'], { token, timeout: TERMINAL_POLL_TIMEOUT_MS })
    } finally {
      await context.close()
    }
  })
})
