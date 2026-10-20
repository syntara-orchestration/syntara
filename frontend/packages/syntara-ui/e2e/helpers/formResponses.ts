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

/** Matches mock `sampleFormDefinition` (Reason field) for side-panel parity. */
export const SIDE_PANEL_REASON_FORM_DEFINITION = {
  fields: [
    {
      value_name: 'reason',
      type: 'text',
      label: 'Reason',
      required: true,
      placeholder: 'Describe why you are approving this change',
    },
  ],
} as const

/** Matches mock `dynamicResolvedFormDefinition` (resolved at run time for UI-14). */
export const ENVIRONMENT_DYNAMIC_RESOLVED_FORM_DEFINITION = {
  fields: [
    {
      value_name: 'environment',
      type: 'dropdown',
      label: 'Environment',
      required: true,
      options: {
        source: 'dynamic_resolved',
        values: [
          { display_label: 'Development', value: 'dev' },
          { display_label: 'Production', value: 'prod' },
        ],
      },
    },
  ],
} as const

/** Static dropdown for environment selection (publishable on real backend). */
export const ENVIRONMENT_DROPDOWN_FORM_DEFINITION = {
  fields: [
    {
      value_name: 'environment',
      type: 'dropdown',
      label: 'Environment',
      required: true,
      options: {
        source: 'static',
        values: [
          { display_label: 'Development', value: 'dev' },
          { display_label: 'Production', value: 'prod' },
        ],
      },
    },
  ],
} as const

export const MULTI_FIELD_FORM_DEFINITION = {
  fields: [
    {
      value_name: 'summary',
      type: 'text',
      label: 'Summary',
      required: true,
      placeholder: 'Describe the change',
    },
    {
      value_name: 'score',
      type: 'number',
      label: 'Score',
      required: false,
      placeholder: 'Optional score',
    },
  ],
} as const

export type FormStepNodeParameters = {
  message?: string
  form_definition?:
    | typeof MINIMAL_FORM_DEFINITION
    | typeof MULTI_FIELD_FORM_DEFINITION
    | typeof SIDE_PANEL_REASON_FORM_DEFINITION
    | typeof ENVIRONMENT_DROPDOWN_FORM_DEFINITION
  submit_label?: string
  success_message?: string
  css_override?: string
  response_window?: number
  /** Workflow schema stores usernames / group names (strings). Objects are normalized before publish. */
  responder_users?: Array<string | { id: string; username: string }>
  responder_groups?: Array<string | { id: string; name: string }>
  fallback_decision?: 'submit' | 'fallback'
}

function normalizeResponderUsersForWorkflowApi(
  users?: Array<string | { id: string; username: string }>
): string[] | undefined {
  if (users === undefined) return undefined
  return users.map((entry) => (typeof entry === 'string' ? entry : entry.username))
}

function normalizeResponderGroupsForWorkflowApi(
  groups?: Array<string | { id: string; name: string }>
): string[] | undefined {
  if (groups === undefined) return undefined
  return groups.map((entry) => (typeof entry === 'string' ? entry : entry.name))
}

export type SidePanelScenario = {
  executionId: string
  pendingId: string
  pendingName: string
  pendingMessage: string
  customSubmitLabel: string
  customSuccessMessage: string
  dynamicPendingId?: string
  dynamicPendingMessage?: string
  workflowId?: string
}

export async function isMockFormPromptSidePanelSeedAvailable(app: Page): Promise<boolean> {
  const seedResp = await apiRequest(app, 'get', `/form_prompts/${MOCK_FORM_RESPONSE_SEED.pendingId}`)
  return seedResp.ok()
}

export async function loadSidePanelScenario(app: Page, namePrefix = 'e2e-side-panel'): Promise<SidePanelScenario> {
  if (await isMockFormPromptSidePanelSeedAvailable(app)) {
    return { ...MOCK_FORM_RESPONSE_SEED }
  }

  if (!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
    throw new Error('Temporal worker required to create form prompt executions on the real backend')
  }

  const pendingMessage = MOCK_FORM_RESPONSE_SEED.pendingMessage
  const customSubmitLabel = MOCK_FORM_RESPONSE_SEED.customSubmitLabel
  const customSuccessMessage = MOCK_FORM_RESPONSE_SEED.customSuccessMessage

  const primary = await createPendingFormStepWorkflow(app, {
    namePrefix,
    parameters: {
      message: pendingMessage,
      form_definition: SIDE_PANEL_REASON_FORM_DEFINITION,
      submit_label: customSubmitLabel,
      success_message: customSuccessMessage,
      responder_users: [],
      responder_groups: [],
    },
  })

  return {
    executionId: primary.executionId,
    pendingId: primary.formPromptId,
    pendingName: primary.promptName,
    pendingMessage,
    customSubmitLabel,
    customSuccessMessage,
    workflowId: primary.workflowId,
  }
}

export async function loadSidePanelEnvironmentScenario(
  app: Page,
  namePrefix = 'e2e-side-panel-env'
): Promise<{
  executionId: string
  dynamicPendingId: string
  dynamicPendingMessage: string
  workflowId?: string
}> {
  if (await isMockFormPromptSidePanelSeedAvailable(app)) {
    return {
      executionId: MOCK_FORM_RESPONSE_SEED.executionId,
      dynamicPendingId: MOCK_FORM_RESPONSE_SEED.dynamicPendingId,
      dynamicPendingMessage: MOCK_FORM_RESPONSE_SEED.dynamicPendingMessage,
    }
  }

  if (!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
    throw new Error('Temporal worker required to create form prompt executions on the real backend')
  }

  const created = await createPendingFormStepWorkflow(app, {
    namePrefix,
    parameters: {
      message: MOCK_FORM_RESPONSE_SEED.dynamicPendingMessage,
      form_definition: ENVIRONMENT_DROPDOWN_FORM_DEFINITION,
      submit_label: MOCK_FORM_RESPONSE_SEED.customSubmitLabel,
      success_message: MOCK_FORM_RESPONSE_SEED.customSuccessMessage,
      responder_users: [],
      responder_groups: [],
    },
  })

  await routeResolvedEnvironmentFormPrompt(app, created.formPromptId)

  return {
    executionId: created.executionId,
    dynamicPendingId: created.formPromptId,
    dynamicPendingMessage: MOCK_FORM_RESPONSE_SEED.dynamicPendingMessage,
    workflowId: created.workflowId,
  }
}

async function routeResolvedEnvironmentFormPrompt(app: Page, promptId: string): Promise<void> {
  await app.route(`**/api/v1/form_prompts/${promptId}`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    let body: Record<string, unknown> = {}
    try {
      const response = await route.fetch()
      const parsed: unknown = await response.json()
      if (typeof parsed === 'object' && parsed !== null) {
        body = parsed as Record<string, unknown>
      }
    } catch {
      // Use synthetic body when the upstream fetch or parse fails.
    }
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        ...body,
        id: promptId,
        status: (body['status'] as string) || 'pending',
        message: MOCK_FORM_RESPONSE_SEED.dynamicPendingMessage,
        form_definition: ENVIRONMENT_DYNAMIC_RESOLVED_FORM_DEFINITION,
      }),
    })
  })
}

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

export function executionIdFromPageUrl(app: Page): string {
  const match = new URL(app.url()).pathname.match(/\/executions\/([^/]+)/)
  if (!match?.[1]) {
    throw new Error('Expected execution detail URL after running a workflow')
  }
  return match[1]
}

export async function disposeFormPromptWorkflow(app: Page, workflowId: string, executionId?: string): Promise<void> {
  if (executionId) {
    try {
      await cancelExecutionViaApi(app, executionId)
    } catch {
      // Best-effort: mock may already be terminal
    }
  }
  await deleteWorkflowViaApi(app, workflowId)
}

/**
 * Create a workflow with a form prompt node and run it to produce a pending list row.
 * On mock: POST /executions synthesizes the form prompt when the run pauses.
 * On real backend: polls for paused execution and list visibility when Temporal is available.
 */
export async function createPendingFormStepWorkflow(
  app: Page,
  options?: {
    namePrefix?: string
    parameters?: FormStepNodeParameters
    runAfterPublish?: boolean
    formPromptNodeId?: string
    formPromptNodeSettings?: { timeout?: number }
    trailingNodes?: Array<{ id: string; type: string; name: string; parameters: Record<string, unknown> }>
    trailingEdges?: Array<{ from: string; to: string; from_port?: string }>
  }
): Promise<{
  workflowId: string
  workflowName: string
  executionId: string
  promptName: string
  formPromptId: string
}> {
  const workflowName = buildUniqueName('e2e-form-step')
  const promptName = buildUniqueName(options?.namePrefix ?? 'form-step')
  const runAfterPublish = options?.runAfterPublish ?? true
  const hasTemporal = !!process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']
  const mockPollTimeout = process.env.CI ? 45_000 : 15_000
  const nodeParameters: FormStepNodeParameters = {
    message: 'E2E form step rendering test',
    form_definition: MINIMAL_FORM_DEFINITION,
    response_window: 600,
    responder_users: [],
    responder_groups: [],
    ...options?.parameters,
  }
  nodeParameters.responder_users = normalizeResponderUsersForWorkflowApi(nodeParameters.responder_users)
  nodeParameters.responder_groups = normalizeResponderGroupsForWorkflowApi(nodeParameters.responder_groups)

  const formPromptNodeId = options?.formPromptNodeId ?? 'form_prompt_1'
  const trailingNodes = options?.trailingNodes ?? [
    {
      id: 'script_1',
      type: 'script',
      name: 'Submitted branch',
      parameters: { language: 'python', code: 'print("submitted")' },
    },
  ]
  const trailingEdges = options?.trailingEdges ?? [{ from: formPromptNodeId, to: 'script_1', from_port: 'submitted' }]

  const { id: workflowId, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: formPromptNodeId,
        type: 'form_prompt',
        name: promptName,
        parameters: nodeParameters,
        ...(options?.formPromptNodeSettings ? { settings: options.formPromptNodeSettings } : {}),
      },
      ...trailingNodes,
    ],
    edges: [{ from: 'trigger_1', to: formPromptNodeId }, ...trailingEdges],
  })

  try {
    await publishWorkflowViaApi(app, workflowId, versionNumber)

    if (!runAfterPublish) {
      return { workflowId, workflowName, executionId: '', promptName, formPromptId: '' }
    }

    const runResp = await apiRequest(app, 'post', '/executions', {
      data: { workflow_id: workflowId, trigger_node_id: 'trigger_1', use_published: true },
    })
    const executionId = readExecutionIdFromCreateResponse(await runResp.json())

    if (hasTemporal) {
      await pollExecutionStatus(app, executionId, ['paused'])
      await pollFormPromptVisible(app, promptName, { timeout: 45_000, executionId })
    } else {
      await pollFormPromptVisible(app, promptName, { timeout: mockPollTimeout, executionId })
    }

    let formPromptId = ''
    await expect(async () => {
      const resp = await apiRequest(app, 'get', `/form_prompts?execution_id=${executionId}&status=pending&limit=100`)
      const match = findFormPromptIdByName(await resp.json(), promptName)
      expect(match).toBeTruthy()
      formPromptId = match ?? ''
    }).toPass({ timeout: mockPollTimeout })

    return { workflowId, workflowName, executionId, promptName, formPromptId }
  } catch (error) {
    await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
    throw error
  }
}

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
  const created = await createPendingFormStepWorkflow(app, {
    namePrefix,
    parameters: {
      message: 'E2E form response list test',
      submit_label: MOCK_FORM_RESPONSE_SEED.customSubmitLabel,
      success_message: MOCK_FORM_RESPONSE_SEED.customSuccessMessage,
    },
  })
  return {
    workflowId: created.workflowId,
    workflowName: created.workflowName,
    executionId: created.executionId,
    promptName: created.promptName,
    formPromptId: created.formPromptId,
  }
}
