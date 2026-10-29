import { type Page, expect, toAppUrl } from '../fixtures'
import { apiRequest, createWorkflowViaApi, deleteWorkflowViaApi, publishWorkflowViaApi } from '../utils/api'

import { buildUniqueName, deleteWorkflow, waitForUIReady } from './workflows'

export const FORM_TRIGGER_FIELD_LABEL = 'Request reason'
export const FORM_TRIGGER_SUBMIT_LABEL = 'Start workflow'
export const STALE_FORM_TRIGGER_NODE_ID = 'form'

type PublishedFormTriggerWorkflow = {
  workflowId: string
  workflowName: string
  triggerNodeId: typeof STALE_FORM_TRIGGER_NODE_ID
}

export async function createPublishedFormTriggerWorkflow(
  app: Page,
  namePrefix: string
): Promise<PublishedFormTriggerWorkflow> {
  const workflowName = buildUniqueName(namePrefix)
  const { id, versionNumber } = await createWorkflowViaApi({
    app,
    name: workflowName,
    triggers: [
      {
        id: STALE_FORM_TRIGGER_NODE_ID,
        type: 'form_trigger',
        name: 'Intake',
        parameters: {
          message: 'Complete the form to run this workflow.',
          submit_label: FORM_TRIGGER_SUBMIT_LABEL,
          form_definition: {
            fields: [
              {
                type: 'text',
                value_name: 'reason',
                label: FORM_TRIGGER_FIELD_LABEL,
                required: true,
              },
            ],
          },
        },
      },
    ],
    nodes: [
      {
        id: 'consumer',
        type: 'script',
        name: 'Consumer',
        parameters: { language: 'python', code: 'print("ok")' },
      },
    ],
    edges: [{ from: STALE_FORM_TRIGGER_NODE_ID, to: 'consumer' }],
  })
  await publishWorkflowViaApi(app, id, versionNumber)
  return { workflowId: id, workflowName, triggerNodeId: STALE_FORM_TRIGGER_NODE_ID }
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
    return 0
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

export async function deleteWorkflowViaApiForStaleTest(app: Page, workflowId: string): Promise<void> {
  const resp = await apiRequest(app, 'delete', `/workflows/${workflowId}`)
  expect(resp.ok()).toBeTruthy()
}

export async function disposeFormTriggerWorkflow(app: Page, workflowId: string, workflowName: string): Promise<void> {
  await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
  await deleteWorkflow(app, workflowName).catch(() => undefined)
}
