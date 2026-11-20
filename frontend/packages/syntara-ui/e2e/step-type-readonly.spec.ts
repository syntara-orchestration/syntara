import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName, openWorkflowInBuilder } from './helpers/workflows'
import {
  apiRequest,
  ensureProject,
  getAuthToken,
  createProjectViaApi,
  deleteProjectViaApi,
  deleteWorkflowViaApi,
  publishWorkflowViaApi,
} from './utils/api'

async function createWaitWorkflow(app: Page, name: string, projectId?: string) {
  const token = await getAuthToken(app)
  const project = projectId ? { id: projectId } : await ensureProject(app)
  if (!token || !project) throw new Error('Workflow setup requires an authenticated project')
  const response = await apiRequest(app, 'post', '/workflows', {
    token,
    data: {
      name,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'trigger', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [{ id: 'wait', type: 'wait', name: 'Wait', parameters: { duration: 1 } }],
        edges: [{ from: 'trigger', to: 'wait' }],
      },
    },
  })
  expect(response.ok()).toBeTruthy()
  const workflow = (await response.json()) as { id: string; current_version: number }
  return { id: workflow.id, versionNumber: workflow.current_version }
}

test.describe('Step-type read-only workflow actions', { tag: '@pr-check' }, () => {
  test('a blocked saved step type keeps the workflow viewable but read-only', async ({ app }) => {
    const workflowName = buildUniqueName('step-type-readonly-builder')
    let workflowId: string | undefined

    try {
      const workflow = await createWaitWorkflow(app, workflowName)
      workflowId = workflow.id
      await publishWorkflowViaApi(app, workflow.id, workflow.versionNumber)

      let permissionCheckUnavailable = true
      await app.route('**/api/v1/authz/can_i', async (route) => {
        const body = route.request().postDataJSON() as {
          resource_type?: string
          resource_labels?: { kind?: string }
        }
        if (body.resource_type === 'step_type' && body.resource_labels?.kind === 'wait') {
          if (permissionCheckUnavailable) {
            await route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
            return
          }
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              allowed: false,
              denied: true,
              denied_by: 'no-waits',
              denial_reason: 'policy_deny',
              denied_scope: 'project',
              denied_project: 'payments',
            }),
          })
          return
        }
        await route.continue()
      })

      await openWorkflowInBuilder(app, workflowName, workflow.id)

      const checkError = 'Unable to check step-type permissions.'
      await expect(app.getByRole('status').filter({ hasText: checkError })).toHaveText(checkError)
      await expect(app.getByText('Danger alert:')).toHaveCount(1)
      permissionCheckUnavailable = false
      await app.getByRole('button', { name: 'Retry permission check' }).click()
      await expect(app.getByRole('status').filter({ hasText: 'Editing is unavailable.' })).toHaveText(
        'Editing is unavailable. This workflow is read-only.'
      )
      await expect(app.getByText('You are viewing this workflow in read-only mode.')).toBeVisible()
      await expect(
        app.getByText("This workflow includes Wait steps, but your assigned policies don't allow you to write them.")
      ).toBeVisible()
      await expect(app.getByRole('textbox', { name: 'Workflow name' })).toBeDisabled()
      await expect(app.getByRole('button', { name: 'Add step' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Save workflow' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Publish workflow' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Run', exact: true })).toBeEnabled()

      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: 'Version history' }).click()
      await app
        .getByRole('listitem')
        .filter({
          has: app.getByRole('button', { name: `Actions for version ${workflow.versionNumber}`, exact: true }),
        })
        .click()
      const restore = app.getByRole('button', { name: 'Restore version' })
      const back = app.getByRole('button', { name: 'Back to editor' })
      const reason = 'You can’t restore this version because you don’t have permission to edit Wait steps.'
      await expect(restore).toBeVisible()
      await expect(restore).toHaveAttribute('aria-disabled', 'true')
      await back.focus()
      await app.keyboard.press('Shift+Tab')
      await expect(restore).toBeFocused()
      await expect(app.getByRole('tooltip')).toHaveText(reason)
      await app.keyboard.press('Enter')
      await expect(app.getByRole('dialog', { name: /restore/i })).toHaveCount(0)
      await back.focus()
      await restore.hover()
      await expect(app.getByRole('tooltip')).toHaveText(reason)
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('step-type permissions stay scoped to each workflow project in the list menu', async ({ app }) => {
    const deniedProjectName = buildUniqueName('step-type-denied-project')
    const allowedProjectName = buildUniqueName('step-type-allowed-project')
    const deniedWorkflowName = buildUniqueName('step-type-denied-workflow')
    const allowedWorkflowName = buildUniqueName('step-type-allowed-workflow')
    let deniedProjectId: string | undefined
    let allowedProjectId: string | undefined
    let deniedWorkflowId: string | undefined
    let allowedWorkflowId: string | undefined

    try {
      const deniedProject = await createProjectViaApi(app, deniedProjectName)
      deniedProjectId = deniedProject.id
      const allowedProject = await createProjectViaApi(app, allowedProjectName)
      allowedProjectId = allowedProject.id
      const deniedWorkflow = await createWaitWorkflow(app, deniedWorkflowName, deniedProject.id)
      deniedWorkflowId = deniedWorkflow.id
      const allowedWorkflow = await createWaitWorkflow(app, allowedWorkflowName, allowedProject.id)
      allowedWorkflowId = allowedWorkflow.id

      await app.route('**/api/v1/authz/can_i', async (route) => {
        const body = route.request().postDataJSON() as {
          resource_type?: string
          resource_labels?: { kind?: string }
          resource_project?: string
        }
        if (
          body.resource_type === 'step_type' &&
          body.resource_labels?.kind === 'wait' &&
          body.resource_project === deniedProject.id
        ) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              allowed: false,
              denied: true,
              denied_by: 'no-waits',
              denial_reason: 'policy_deny',
              denied_scope: 'project',
              denied_project: 'payments',
            }),
          })
          return
        }
        await route.continue()
      })

      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      await app.getByPlaceholder('Filter by name').fill(deniedWorkflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const deniedRow = app.getByRole('row').filter({ hasText: deniedWorkflowName })
      await expect(deniedRow).toBeVisible()
      const deniedMenuToggle = deniedRow.getByRole('button', { name: `Actions for ${deniedWorkflowName}` })
      await deniedMenuToggle.focus()
      await deniedMenuToggle.press('Enter')
      const deniedEditAction = app.getByRole('menuitem', { name: 'Edit workflow' })
      await expect(deniedEditAction).toHaveAttribute('aria-disabled', 'true')
      await app.keyboard.press('ArrowDown')
      await expect(deniedEditAction).toBeFocused()
      await app.keyboard.press('Enter')
      await expect(app).toHaveURL(/\/workflows/)

      await app.keyboard.press('Escape')
      await app.getByPlaceholder('Filter by name').fill(allowedWorkflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const allowedRow = app.getByRole('row').filter({ hasText: allowedWorkflowName })
      await expect(allowedRow).toBeVisible()
      await allowedRow.getByRole('button', { name: `Actions for ${allowedWorkflowName}` }).click()
      await expect(app.getByRole('menuitem', { name: 'Edit workflow' })).not.toHaveAttribute('aria-disabled', 'true')
    } finally {
      if (deniedWorkflowId) await deleteWorkflowViaApi(app, deniedWorkflowId)
      if (allowedWorkflowId) await deleteWorkflowViaApi(app, allowedWorkflowId)
      if (deniedProjectId) await deleteProjectViaApi(app, deniedProjectId)
      if (allowedProjectId) await deleteProjectViaApi(app, allowedProjectId)
    }
  })
})
