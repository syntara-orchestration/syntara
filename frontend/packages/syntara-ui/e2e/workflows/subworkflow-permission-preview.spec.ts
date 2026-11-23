import { test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName, clickNode, saveWorkflow } from '../helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi, publishWorkflowViaApi } from '../utils/api'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

test('shows an advisory when the editor cannot execute the selected child workflow', async ({ app }) => {
  const childName = buildUniqueName('e2e-permission-child')
  const parentName = buildUniqueName('e2e-permission-parent')
  let childWorkflowId: string | undefined
  let parentWorkflowId: string | undefined

  try {
    const child = await createWorkflowViaApi({
      app,
      name: childName,
      triggers: [
        {
          id: 'child_entry',
          type: 'subworkflow_trigger',
          name: 'Child entry',
          parameters: { input_schema: { type: 'object', properties: {} } },
        },
      ],
    })
    childWorkflowId = child.id
    await publishWorkflowViaApi(app, child.id, child.versionNumber)

    const parent = await createWorkflowViaApi({
      app,
      name: parentName,
      triggers: [{ id: 'parent_entry', type: 'manual_trigger', name: 'Parent entry', parameters: {} }],
      nodes: [
        {
          id: 'call_child',
          type: 'sub_workflow',
          name: 'Call child',
          parameters: { workflow_id: child.id, trigger_node_id: 'child_entry', input_mapping: {} },
        },
      ],
      edges: [{ from: 'parent_entry', to: 'call_child' }],
    })
    parentWorkflowId = parent.id

    let deniedExecutionCheckMocked = false
    await app.route('**/authz/can_i', async (route) => {
      const body: unknown = route.request().postDataJSON()
      if (isRecord(body) && body.action === 'run' && body.resource_type === 'execution') {
        deniedExecutionCheckMocked = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ allowed: false, denied: true, denial_reason: 'No matching policy' }),
        })
        return
      }
      // Keep unrelated permission checks deterministic too. If the request shape changes,
      // this allows the UI through and the expected denied-check assertion below fails.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ allowed: true, denied: false, denial_reason: null }),
      })
    })

    await app.goto(toAppUrl(`/workflow-builder/${parent.id}`))
    await clickNode(app, 'Call child')

    await expect.poll(() => deniedExecutionCheckMocked).toBe(true)
    await expect(
      app.getByRole('heading', { name: /You may not be able to run executions in this project/ })
    ).toBeVisible()
    const updateButton = app.getByRole('button', { name: 'Update', exact: true })
    await expect(updateButton).toBeEnabled()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Call child permission preview')
    await updateButton.click()
    await expect(updateButton).not.toBeAttached()
    await saveWorkflow(app, parentName)
  } finally {
    if (parentWorkflowId) await deleteWorkflowViaApi(app, parentWorkflowId)
    if (childWorkflowId) await deleteWorkflowViaApi(app, childWorkflowId)
  }
})
