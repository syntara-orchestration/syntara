import type { Locator } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import {
  apiRequest,
  cancelExecutionViaApi,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  pollExecutionStatus,
  pollFormPromptVisible,
  publishWorkflowViaApi,
} from '../utils/api'

import { buildUniqueName } from './workflows'

/** Mock API seed rows used by form-responses and side-panel E2E (see syntara-mock-api formPrompts). */
export const MOCK_FORM_RESPONSE_SEED = {
  pendingName: 'Collect operator input',
  submittedName: 'Confirm deployment details',
  pendingId: 'fp-exec-form-prompt-1',
  dynamicPendingId: 'fp-exec-form-prompt-dynamic',
  executionId: 'exec-form-prompt',
  pendingMessage: 'Provide details required to continue the workflow.',
  dynamicPendingMessage: 'Choose where to deploy.',
  customSubmitLabel: 'Submit response',
  customSuccessMessage: 'Thank you — the workflow will continue.',
  submittedDataSnippet: 'Approved for production rollout',
  defaultProjectName: 'default',
  otherProjectName: 'alice-sandbox',
  otherProjectPendingName: 'Sandbox access review',
} as const

const MINIMAL_FORM_DEFINITION = {
  fields: [
    {
      value_name: 'answer',
      type: 'text',
      label: 'Answer',
      required: true,
      placeholder: 'Enter a value',
    },
  ],
} as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readExecutionIdFromCreateResponse(body: unknown): string {
  if (!isRecord(body)) {
    throw new Error('POST /executions returned a non-object body')
  }
  const id = body['id']
  if (typeof id === 'string' && id.length > 0) return id
  const executionId = body['execution_id']
  if (typeof executionId === 'string' && executionId.length > 0) return executionId
  throw new Error('POST /executions did not return an execution ID')
}

function findFormPromptIdByName(body: unknown, promptName: string): string | undefined {
  if (!isRecord(body)) return undefined
  const resources = body['resources']
  if (!Array.isArray(resources)) return undefined
  for (const row of resources) {
    if (!isRecord(row)) continue
    const name = row['name']
    const id = row['id']
    if (name === promptName && typeof id === 'string' && id.length > 0) return id
  }
  return undefined
}

/** Project selector on Tasks (placeholder before selection, labeled textbox after). */
export function tasksProjectSelector(app: Page): Locator {
  return app.getByRole('textbox', { name: 'Project' }).or(app.getByPlaceholder('All projects'))
}

export async function openFormResponsesTab(app: Page): Promise<Locator> {
  await app.goto(toAppUrl('/tasks/form-responses'))
  await expect(app.getByRole('heading', { level: 1, name: 'Tasks' })).toBeVisible()
  await expect(app.getByRole('tab', { name: 'Form responses', selected: true })).toBeVisible()

  const table = app.getByRole('grid', { name: 'Form responses table' })
  await expect(table).toBeVisible({ timeout: 15_000 })
  return table
}

export async function applyFormResponseNameFilter(
  app: Page,
  table: Locator,
  nameFilter: string,
  options?: { waitForRowText?: string }
): Promise<void> {
  await app.getByPlaceholder('Filter by name').fill(nameFilter)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })).toBeVisible({
    timeout: 15_000,
  })

  if (options?.waitForRowText) {
    await expect(table.getByRole('row').filter({ hasText: options.waitForRowText })).toBeVisible({
      timeout: 15_000,
    })
  }
}

/**
 * Adds a status filter via the filter bar. Call only when a name filter chip is already active
 * (the field selector still shows "Name" until another filter type is chosen).
 */
export async function applyFormResponseStatusFilter(app: Page, statusLabel: string): Promise<void> {
  const filters = app.getByRole('search', { name: 'Filters' })
  await filters.getByRole('button', { name: 'Name', exact: true }).click()
  await app.getByRole('option', { name: 'Status' }).click()
  await app.getByRole('button', { name: 'Filter by status' }).click()
  await app.getByRole('menuitem', { name: statusLabel }).click()

  await expect(
    app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' }).getByText(statusLabel)
  ).toBeVisible({ timeout: 15_000 })
}

export async function disposeFormPromptWorkflow(app: Page, workflowId: string, executionId: string): Promise<void> {
  try {
    await cancelExecutionViaApi(app, executionId)
  } catch {
    // Best-effort: mock may already be terminal
  }
  await deleteWorkflowViaApi(app, workflowId)
}

/**
 * Create a workflow with a form prompt node and run it to produce a pending list row.
 * On mock: POST /executions synthesizes the form prompt when the run pauses.
 * On real backend: polls for paused execution and list visibility when Temporal is available.
 */
export async function createPendingFormPromptLight(
  app: Page,
  namePrefix = 'form-prompt'
): Promise<{
  workflowId: string
  workflowName: string
  executionId: string
  promptName: string
  formPromptId: string
}> {
  const workflowName = buildUniqueName('e2e-form-response')
  const promptName = buildUniqueName(namePrefix)
  const hasTemporal = !!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']

  const { id: workflowId, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: 'form_prompt_1',
        type: 'form_prompt',
        name: promptName,
        parameters: {
          message: 'E2E form response list test',
          form_definition: MINIMAL_FORM_DEFINITION,
          response_window: 600,
        },
      },
      {
        id: 'script_1',
        type: 'script',
        name: `${promptName} - submitted action`,
        parameters: { language: 'python', code: 'print("submitted")' },
      },
    ],
    edges: [
      { from: 'trigger_1', to: 'form_prompt_1' },
      { from: 'form_prompt_1', to: 'script_1', from_port: 'submitted' },
    ],
  })

  try {
    await publishWorkflowViaApi(app, workflowId, versionNumber)

    const runResp = await apiRequest(app, 'post', '/executions', {
      data: { workflow_id: workflowId, trigger_node_id: 'trigger_1', use_published: true },
    })
    const executionId = readExecutionIdFromCreateResponse(await runResp.json())

    if (hasTemporal) {
      await pollExecutionStatus(app, executionId, ['paused'])
      await pollFormPromptVisible(app, promptName, { timeout: 45_000 })
    } else {
      await pollFormPromptVisible(app, promptName, { timeout: 15_000 })
    }

    let formPromptId = ''
    await expect(async () => {
      const resp = await apiRequest(app, 'get', `/form_prompts?execution_id=${executionId}&status=pending&limit=100`)
      const match = findFormPromptIdByName(await resp.json(), promptName)
      expect(match).toBeTruthy()
      formPromptId = match ?? ''
    }).toPass({ timeout: 15_000 })

    return { workflowId, workflowName, executionId, promptName, formPromptId }
  } catch (error) {
    await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
    throw error
  }
}
