import { ActivityTypeEnum } from '@syntara/contracts'

import { test, expect, toAppUrl } from '../fixtures'
import { clickAddConnectedStep } from '../helpers/add-connected-step'
import { selectCategoryAndType } from '../helpers/v2-nodes'
import { buildUniqueName, closeNodeEditorPanel, saveWorkflow } from '../helpers/workflows'
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
