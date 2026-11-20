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

test('input picker exposes declared outputs without exposing a large child workflow’s internal steps', async ({
  app,
}) => {
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
              properties: {
                release: {
                  type: 'object',
                  properties: { artifact_url: { type: 'string', description: 'URL for the built artifact' } },
                  required: ['artifact_url'],
                },
              },
              required: ['release'],
            },
            output_mapping: { 'release.artifact_url': '${child_step_63.stdout}' },
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
          parameters: { prompt: 'Release artifact: ' },
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
    await expect(inputPanel.getByText('T child_workflow_id', { exact: true })).toBeVisible()
    const outputLeaf = inputPanel.getByText('T artifact_url', { exact: true })
    if (!(await outputLeaf.isVisible())) await childSection.click()

    await expect(outputLeaf).toBeVisible()
    await expect(inputPanel.getByText('Child step 63', { exact: false })).not.toBeVisible()

    await app.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    const expression = '${invoke_large_child.outputs.release.artifact_url}'
    await outputLeaf.hover()
    await inputPanel.getByRole('button', { name: `Copy expression ${expression}` }).click()

    const outputTreeItem = inputPanel.getByRole('treeitem', { name: /T artifact_url/ })
    await expect(outputTreeItem.getByRole('status')).toContainText('Expression copied to clipboard')
    const prompt = app.getByRole('textbox', { name: 'Prompt', exact: true })
    await prompt.click()
    await app.keyboard.press('ControlOrMeta+V')
    await expect(prompt).toHaveValue(`Release artifact: ${expression}`)
  } finally {
    if (parentWorkflowId) await deleteWorkflowViaApi(app, parentWorkflowId)
    if (childWorkflowId) await deleteWorkflowViaApi(app, childWorkflowId)
  }
})

test('shows an access warning and hides declared outputs when the child schema request is forbidden', async ({
  app,
}) => {
  const childName = buildUniqueName('e2e-subworkflow-forbidden-child')
  const parentName = buildUniqueName('e2e-subworkflow-forbidden-parent')
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
            input_schema: { type: 'object', properties: {} },
            output_schema: {
              type: 'object',
              properties: { private_result: { type: 'string', description: 'Private child result' } },
            },
            output_mapping: { private_result: '${child_script.stdout}' },
          },
        },
      ],
      nodes: [
        {
          id: 'child_script',
          type: 'script',
          name: 'Produce child result',
          parameters: { language: 'python', code: 'print("private")' },
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
          id: 'invoke_protected_child',
          type: ActivityTypeEnum.SUB_WORKFLOW,
          name: 'Invoke protected child',
          parameters: {
            workflow_id: child.id,
            trigger_node_id: 'child_subworkflow_trigger',
            input_mapping: {},
          },
        },
        {
          id: 'consume_protected_output',
          type: ActivityTypeEnum.SCRIPT,
          name: 'Consume protected output',
          parameters: { language: 'python', code: 'print("consumer")' },
        },
      ],
      edges: [
        { from: 'parent_manual_trigger', to: 'invoke_protected_child' },
        { from: 'invoke_protected_child', to: 'consume_protected_output' },
      ],
    })
    parentWorkflowId = parent.id

    // The mock API does not model per-workflow read grants; simulate the backend's denied schema response.
    await app.route(`**/api/v1/workflows/${child.id}/invocation_schema`, (route) =>
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Forbidden', code: 'WORKFLOW_ACCESS_DENIED' }),
      })
    )

    await app.goto(toAppUrl(`/workflow-builder/${parent.id}`))
    await clickNode(app, 'Invoke protected child')
    await expect(app.getByText('You do not have permission to read this child workflow.')).toBeVisible()
    await closeNodeEditorPanel(app)

    await clickNode(app, 'Consume protected output')
    const inputPanel = app.locator('[class*="panelContainer"]').filter({
      has: app.getByRole('heading', { name: 'Input', exact: true }),
    })
    await expect(inputPanel.getByText('Declared child outputs are unavailable')).toBeVisible()
    await expect(
      inputPanel.getByText("You need permission to view the child workflow's declared output contract.")
    ).toBeVisible()
    await expect(inputPanel.getByText('T child_workflow_id', { exact: true })).toBeVisible()
    await expect(inputPanel.getByText('T private_result', { exact: true })).toHaveCount(0)
  } finally {
    if (parentWorkflowId) await deleteWorkflowViaApi(app, parentWorkflowId)
    if (childWorkflowId) await deleteWorkflowViaApi(app, childWorkflowId)
  }
})
