import { expect, type Page, toAppUrl } from '../fixtures'
import { apiRequest, createWorkflowViaApi, deleteWorkflowViaApi, publishWorkflowViaApi } from '../utils/api'

import { MULTI_FIELD_FORM_DEFINITION } from './formResponses'
import { clickRunPublishedVersionFromWorkflowList } from './workflow-run'
import { buildUniqueName, deleteWorkflow, waitForUIReady } from './workflows'

export const FORM_TRIGGER_FIELD_LABEL = 'Request reason'
export const FORM_TRIGGER_SUBMIT_LABEL = 'Start workflow'
export const STALE_FORM_TRIGGER_NODE_ID = 'form'

export type FormTriggerNodeParameters = {
  message?: string
  form_definition?: Record<string, unknown>
  submit_label?: string
  success_message?: string
  css_override?: string
}

const DEFAULT_FORM_TRIGGER_PARAMETERS: FormTriggerNodeParameters = {
  message: 'Complete the form to start this workflow.',
  form_definition: MULTI_FIELD_FORM_DEFINITION,
}

const DEFAULT_CONSUMER_NODE = {
  id: 'script_1',
  type: 'script',
  name: 'Consumer',
  parameters: { language: 'python', code: 'print("form-trigger-run")' },
} as const

const STALE_POPUP_CONSUMER_NODE = {
  id: 'consumer',
  type: 'script',
  name: 'Consumer',
  parameters: { language: 'python', code: 'print("ok")' },
} as const

const STALE_POPUP_FORM_DEFINITION = {
  fields: [
    {
      type: 'text',
      value_name: 'reason',
      label: FORM_TRIGGER_FIELD_LABEL,
      required: true,
    },
  ],
} as const

export type PublishedFormTriggerWorkflow = {
  workflowId: string
  workflowName: string
  triggerNodeId: string
  triggerName: string
}

type CreatePublishedFormTriggerOptions = {
  namePrefix?: string
  triggerId?: string
  triggerName?: string
  parameters?: FormTriggerNodeParameters
  consumerNode?: typeof DEFAULT_CONSUMER_NODE | typeof STALE_POPUP_CONSUMER_NODE
}

async function createPublishedFormTriggerWorkflowInternal(
  app: Page,
  options: CreatePublishedFormTriggerOptions
): Promise<PublishedFormTriggerWorkflow> {
  const workflowName = buildUniqueName(options.namePrefix ?? 'e2e-form-trigger-run')
  const triggerNodeId = options.triggerId ?? 'form_trigger_1'
  const triggerName = options.triggerName ?? 'Request intake'
  const consumerNode = options.consumerNode ?? DEFAULT_CONSUMER_NODE
  const parameters: FormTriggerNodeParameters = { ...DEFAULT_FORM_TRIGGER_PARAMETERS, ...options.parameters }
  if (options.parameters && Object.hasOwn(options.parameters, 'form_definition')) {
    if (options.parameters.form_definition === undefined) {
      delete parameters.form_definition
    } else {
      parameters.form_definition = options.parameters.form_definition
    }
  }

  const { id: workflowId, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [
      {
        id: triggerNodeId,
        type: 'form_trigger',
        name: triggerName,
        parameters,
      },
    ],
    nodes: [consumerNode],
    edges: [{ from: triggerNodeId, to: consumerNode.id }],
  })

  try {
    await publishWorkflowViaApi(app, workflowId, versionNumber)
    return { workflowId, workflowName, triggerNodeId, triggerName }
  } catch (error) {
    await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
    throw error
  }
}

/** UI-19 stale-popup fixtures use a string name prefix and legacy trigger node id `form`. */
export async function createPublishedFormTriggerWorkflow(
  app: Page,
  namePrefix: string
): Promise<PublishedFormTriggerWorkflow>
export async function createPublishedFormTriggerWorkflow(
  app: Page,
  options?: CreatePublishedFormTriggerOptions
): Promise<PublishedFormTriggerWorkflow>
export async function createPublishedFormTriggerWorkflow(
  app: Page,
  namePrefixOrOptions?: string | CreatePublishedFormTriggerOptions
): Promise<PublishedFormTriggerWorkflow> {
  if (typeof namePrefixOrOptions === 'string') {
    return createPublishedFormTriggerWorkflowInternal(app, {
      namePrefix: namePrefixOrOptions,
      triggerId: STALE_FORM_TRIGGER_NODE_ID,
      triggerName: 'Intake',
      consumerNode: STALE_POPUP_CONSUMER_NODE,
      parameters: {
        message: 'Complete the form to run this workflow.',
        submit_label: FORM_TRIGGER_SUBMIT_LABEL,
        form_definition: STALE_POPUP_FORM_DEFINITION,
      },
    })
  }
  return createPublishedFormTriggerWorkflowInternal(app, namePrefixOrOptions ?? {})
}

function stripFormDefinitionFromWorkflowDefinition(definition: unknown): void {
  if (!definition || typeof definition !== 'object') return
  const triggers = (definition as { triggers?: unknown[] }).triggers
  if (!Array.isArray(triggers)) return
  for (const trigger of triggers) {
    if (!trigger || typeof trigger !== 'object') continue
    const typed = trigger as { type?: string; parameters?: Record<string, unknown> }
    if (typed.type !== 'form_trigger' || !typed.parameters) continue
    delete typed.parameters.form_definition
  }
}

function stripFormDefinitionFromWorkflowApiBody(body: unknown): void {
  if (!body || typeof body !== 'object') return
  const record = body as {
    workflow_definition?: unknown
    version?: { workflow_definition?: unknown }
  }
  stripFormDefinitionFromWorkflowDefinition(record.workflow_definition)
  stripFormDefinitionFromWorkflowDefinition(record.version?.workflow_definition)
}

export function formTriggerWorkflowApiRoute(workflowId: string): string {
  return `**/api/v1/workflows/${workflowId}**`
}

/** Simulates a published form trigger whose definition cannot be loaded at run time (real backend rejects omitting form_definition at publish). */
export async function registerStripFormDefinitionFromWorkflowApi(app: Page, workflowId: string): Promise<void> {
  const pattern = formTriggerWorkflowApiRoute(workflowId)
  await app.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    const response = await route.fetch()
    const headers = response.headers()
    if (!response.ok()) {
      await route.fulfill({ status: response.status(), headers, body: await response.body() })
      return
    }
    const body = (await response.json()) as unknown
    stripFormDefinitionFromWorkflowApiBody(body)
    await route.fulfill({
      status: response.status(),
      headers,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

export async function unregisterStripFormDefinitionFromWorkflowApi(app: Page, workflowId: string): Promise<void> {
  await app.unroute(formTriggerWorkflowApiRoute(workflowId))
}

export async function openFormTriggerRunDialogFromWorkflowList(app: Page, workflowName: string): Promise<void> {
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const row = app.getByRole('row', { name: new RegExp(workflowName) })
  await expect(row).toBeVisible({ timeout: 15_000 })
  await waitForUIReady(app)

  await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
  await app.getByRole('menuitem', { name: 'Run published version' }).click()

  await expect(app.getByRole('dialog')).toBeVisible({ timeout: 20_000 })
  await expect(app.getByTestId('form-trigger-run-form')).toBeVisible()
  await expect(app.getByRole('button', { name: 'Run now' })).not.toBeVisible()
}

export async function countExecutionsForWorkflow(app: Page, workflowId: string): Promise<number> {
  const resp = await apiRequest(app, 'get', `/executions?workflow_id=${workflowId}&limit=100`)
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`GET /executions?workflow_id=${workflowId} returned ${resp.status()}: ${body}`)
  }
  const body = (await resp.json()) as { resources?: unknown[] }
  return body.resources?.length ?? 0
}

export async function republishWorkflowWithoutFormTrigger(
  app: Page,
  workflowId: string,
  workflowName: string
): Promise<void> {
  const patchResp = await apiRequest(app, 'patch', `/workflows/${workflowId}`, {
    data: {
      workflow_definition: {
        schema_version: '2.0.0',
        name: workflowName,
        triggers: [{ id: 'manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [
          {
            id: 'consumer',
            type: 'script',
            name: 'Consumer',
            parameters: { language: 'python', code: 'print("ok")' },
          },
        ],
        edges: [{ from: 'manual', to: 'consumer' }],
      },
    },
  })
  if (!patchResp.ok()) {
    const body = await patchResp.text().catch(() => '(unreadable)')
    throw new Error(`PATCH /workflows/${workflowId} returned ${patchResp.status()}: ${body}`)
  }
  const patched = (await patchResp.json()) as { current_version: number }
  await publishWorkflowViaApi(app, workflowId, patched.current_version)
}

export async function expectStaleFormTriggerSubmitBlocked(
  app: Page,
  workflowId: string,
  triggerNodeId: string
): Promise<void> {
  const dialog = app.getByRole('dialog')
  await dialog.getByRole('textbox', { name: FORM_TRIGGER_FIELD_LABEL }).fill('late answer')
  const executionCountBefore = await countExecutionsForWorkflow(app, workflowId)

  await dialog.getByRole('button', { name: FORM_TRIGGER_SUBMIT_LABEL }).click()

  await expect(dialog.getByText('Unable to submit this form. Try again or contact your administrator.')).toBeVisible({
    timeout: 15_000,
  })
  await expect(dialog).toBeVisible()
  await expect(app).not.toHaveURL(/\/executions\//)

  await expect(async () => {
    expect(await countExecutionsForWorkflow(app, workflowId)).toBe(executionCountBefore)
  }).toPass({ timeout: 10_000 })

  await expect(async () => {
    const resp = await apiRequest(app, 'post', '/executions', {
      data: {
        workflow_id: workflowId,
        trigger_node_id: triggerNodeId,
        input_data: { reason: 'late answer' },
        use_published: true,
      },
    })
    expect(resp.status()).toBeGreaterThanOrEqual(400)
  }).toPass({ timeout: 10_000 })
}

export async function disposeFormTriggerWorkflow(app: Page, workflowId: string, workflowName?: string): Promise<void> {
  await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
  if (workflowName) {
    await deleteWorkflow(app, workflowName).catch(() => undefined)
  }
}

/** Kebab → Run published version. Form triggers skip the manual confirmation dialog. */
export async function startRunPublishedFromWorkflowList(app: Page, workflowName: string): Promise<void> {
  await clickRunPublishedVersionFromWorkflowList(app, workflowName)
}

export async function expectFormTriggerRunModal(
  app: Page,
  options: { workflowName: string; triggerName: string; message?: string }
): Promise<void> {
  await expect(app.getByRole('dialog', { name: new RegExp(`Run ${options.triggerName} form`) })).toBeVisible({
    timeout: 15_000,
  })
  await expect(app.getByRole('heading', { name: `Run ${options.workflowName}` })).toBeVisible()
  if (options.message) {
    await expect(app.getByText(options.message)).toBeVisible()
  }
  await expect(app.getByTestId('form-trigger-run-form')).toBeVisible()
}

export async function readExecutionInputData(app: Page, executionId: string): Promise<Record<string, unknown>> {
  const resp = await apiRequest(app, 'get', `/executions/${executionId}`)
  expect(resp.ok()).toBeTruthy()
  const body = (await resp.json()) as { input_data?: Record<string, unknown> }
  return body.input_data ?? {}
}
