import { ActivityTypeEnum } from '@syntara/contracts'

import { test, expect, toAppUrl } from '../fixtures'
import { clickAddConnectedStep } from '../helpers/add-connected-step'
import { selectCategoryAndType } from '../helpers/v2-nodes'
import { buildUniqueName, clickNode, closeNodeEditorPanel, saveWorkflow } from '../helpers/workflows'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  publishWorkflowViaApi,
} from '../utils/api'

type SavedWorkflow = {
  version?: {
    workflow_definition?: {
      nodes?: Array<{ id?: string; type?: string; parameters?: Record<string, unknown> }>
    }
  }
}

test('designer selects a published child, maps its inputs, and saves the Sub-workflow step', async ({ app }) => {
  const childName = buildUniqueName('e2e-subworkflow-child')
  const parentName = buildUniqueName('e2e-subworkflow-parent')
  let childWorkflowId: string | undefined
  let parentWorkflowId: string | undefined

  try {
    const child = await createWorkflowViaApi({
      app,
      name: childName,
      triggers: [
        {
          id: 'child_subworkflow_trigger',
          type: 'subworkflow_trigger',
          name: 'Child invocation',
          parameters: {
            input_schema: {
              type: 'object',
              required: ['host'],
              properties: { host: { type: 'string' } },
            },
          },
        },
      ],
      nodes: [
        {
          id: 'child_script',
          type: 'script',
          name: 'Echo input',
          parameters: { language: 'python', code: 'print("hello")' },
        },
      ],
      edges: [{ from: 'child_subworkflow_trigger', to: 'child_script' }],
    })
    childWorkflowId = child.id
    await publishWorkflowViaApi(app, child.id, child.versionNumber)

    const parent = await createWorkflowViaApi({
      app,
      name: parentName,
      triggers: [{ id: 'parent_manual_trigger', type: 'manual_trigger', name: 'Start', parameters: {} }],
      nodes: [
        {
          id: 'parent_script',
          type: 'script',
          name: 'Prepare data',
          parameters: { language: 'python', code: 'print("parent")' },
        },
      ],
      edges: [{ from: 'parent_manual_trigger', to: 'parent_script' }],
    })
    parentWorkflowId = parent.id

    await app.goto(toAppUrl(`/workflow-builder/${parent.id}`))
    await expect(app.getByText('Prepare data')).toBeVisible()
    await clickAddConnectedStep(app)
    await selectCategoryAndType(app, 'Action', 'Sub-workflow')

    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Invoke child workflow')
    await app.getByPlaceholder('Search for a published workflow...').click()
    await app.getByRole('option', { name: new RegExp(childName) }).click()
    await app.getByRole('textbox', { name: 'host', exact: true }).fill('parent-host.example')
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await closeNodeEditorPanel(app)

    await saveWorkflow(app, parentName)

    const token = await getAuthToken(app)
    if (!token) throw new Error('Could not obtain an auth token to verify the saved workflow')
    const response = await apiRequest(app, 'get', `/workflows/${parent.id}`, { token })
    expect(response.ok()).toBe(true)
    const savedWorkflow = (await response.json()) as SavedWorkflow
    const subWorkflowNode = savedWorkflow.version?.workflow_definition?.nodes?.find(
      (node) => node.type === ActivityTypeEnum.SUB_WORKFLOW
    )

    expect(subWorkflowNode?.parameters).toMatchObject({
      workflow_id: child.id,
      trigger_node_id: 'child_subworkflow_trigger',
      input_mapping: { host: 'parent-host.example' },
    })
  } finally {
    if (parentWorkflowId) await deleteWorkflowViaApi(app, parentWorkflowId)
    if (childWorkflowId) await deleteWorkflowViaApi(app, childWorkflowId)
  }
})

test('input picker exposes declared nested outputs and inserts their expression for a large child', async ({ app }) => {
  const childName = buildUniqueName('e2e-subworkflow-large-child')
  const parentName = buildUniqueName('e2e-subworkflow-large-parent')
  let childWorkflowId: string | undefined
  let parentWorkflowId: string | undefined

  try {
    const childSteps = Array.from({ length: 64 }, (_, index) => ({
      id: `child_step_${index}`,
      name: `Child step ${index}`,
      type: 'script',
      parameters: { language: 'python', code: `print(${index})` },
    }))
    const child = await createWorkflowViaApi({
      app,
      name: childName,
      triggers: [
        {
          id: 'child_subworkflow_trigger',
          type: 'subworkflow_trigger',
          name: 'Child invocation',
          parameters: {
            input_schema: { type: 'object', properties: {} },
            output_schema: {
              type: 'object',
              required: ['release'],
              properties: {
                release: {
                  type: 'object',
                  description: 'Release metadata',
                  required: ['version'],
                  properties: {
                    version: { type: 'string', description: 'Published release version' },
                  },
                },
              },
            },
            output_mapping: {
              'release.version': '${child_step_63.stdout}',
            },
          },
        },
      ],
      nodes: childSteps,
      edges: childSteps.map((step) => ({ from: 'child_subworkflow_trigger', to: step.id })),
    })
    childWorkflowId = child.id
    await publishWorkflowViaApi(app, child.id, child.versionNumber)

    const parent = await createWorkflowViaApi({
      app,
      name: parentName,
      triggers: [{ id: 'parent_manual_trigger', type: 'manual_trigger', name: 'Start', parameters: {} }],
      nodes: [
        {
          id: 'invoke_large_child',
          type: ActivityTypeEnum.SUB_WORKFLOW,
          name: 'Invoke large child',
          parameters: {
            workflow_id: child.id,
            trigger_node_id: 'child_subworkflow_trigger',
            input_mapping: {},
          },
        },
        {
          id: 'consume_child_outputs',
          type: ActivityTypeEnum.AGENTIC,
          name: 'Consume child outputs',
          parameters: { prompt: 'Release version: ', tool_selection_strategy: 'NONE' },
        },
      ],
      edges: [
        { from: 'parent_manual_trigger', to: 'invoke_large_child' },
        { from: 'invoke_large_child', to: 'consume_child_outputs' },
      ],
    })
    parentWorkflowId = parent.id

    await app.goto(toAppUrl(`/workflow-builder/${parent.id}`))
    await clickNode(app, 'Consume child outputs')
    await expect(app.getByRole('heading', { name: 'Input', exact: true })).toBeVisible()

    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    const childSection = inputPanel.getByRole('button', { name: 'Invoke large child', exact: true })
    await expect(childSection).toBeVisible()
    const childWorkflowIdField = inputPanel.getByText('T child_workflow_id', { exact: true })
    if (!(await childWorkflowIdField.isVisible())) await childSection.click()

    await expect(childWorkflowIdField).toBeVisible({ timeout: 30_000 })
    await expect(inputPanel.getByText('T child_status', { exact: true })).toBeVisible()
    await expect(inputPanel.getByText('{} outputs', { exact: true })).toBeVisible()
    await expect(inputPanel.getByText('{} release', { exact: true })).toBeVisible()

    const releaseGroup = inputPanel.getByRole('treeitem', { name: /\{\} release/ })
    await releaseGroup.getByRole('button', { name: /\{\} release/ }).click()

    const nestedOutput = inputPanel
      .getByRole('tree', { name: 'Schema preview' })
      .locator('[draggable="true"]')
      .filter({ hasText: 'T version' })
    await expect(nestedOutput).toBeVisible()
    await expect(inputPanel.getByText('Child step 63', { exact: false })).not.toBeAttached()

    const promptField = app.getByRole('textbox', { name: 'Prompt', exact: true })
    await expect(nestedOutput).toHaveCount(1)
    await expect(promptField).toHaveValue('Release version: ')
    await nestedOutput.hover()
    await nestedOutput.dragTo(promptField)
    await expect(promptField).toHaveValue('Release version: ${invoke_large_child.outputs.release.version}')
  } finally {
    if (parentWorkflowId) await deleteWorkflowViaApi(app, parentWorkflowId)
    if (childWorkflowId) await deleteWorkflowViaApi(app, childWorkflowId)
  }
})
