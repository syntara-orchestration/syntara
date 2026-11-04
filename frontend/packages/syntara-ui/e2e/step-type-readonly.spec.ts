import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, openWorkflowInBuilder } from './helpers/workflows'
import {
  createBasicWorkflowViaApi,
  createProjectViaApi,
  deleteProjectViaApi,
  deleteWorkflowViaApi,
  publishWorkflowViaApi,
} from './utils/api'

test.describe('Step-type read-only workflow actions', { tag: '@pr-check' }, () => {
  test('a blocked saved step type keeps the workflow viewable but read-only', async ({ app }) => {
    const workflowName = buildUniqueName('step-type-readonly-builder')
    let workflowId: string | undefined

    try {
      const workflow = await createBasicWorkflowViaApi(app, workflowName)
      workflowId = workflow.id
      await publishWorkflowViaApi(app, workflow.id, workflow.versionNumber)

      await app.route('**/api/v1/authz/can_i', async (route) => {
        const body = route.request().postDataJSON() as {
          resource_type?: string
          resource_labels?: { kind?: string }
        }
        if (body.resource_type === 'step_type' && body.resource_labels?.kind === 'script') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ allowed: false }),
          })
          return
        }
        await route.continue()
      })

      await openWorkflowInBuilder(app, workflowName, workflow.id)

      await expect(app.getByText('You are viewing this workflow in read-only mode.')).toBeVisible()
      await expect(app.getByText('Blocked step types: Script.')).toBeVisible()
      await expect(app.getByRole('textbox', { name: 'Workflow name' })).toBeDisabled()
      await expect(app.getByRole('button', { name: 'Add step' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Save workflow' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Publish workflow' })).toHaveAttribute('aria-disabled', 'true')
      await expect(app.getByRole('button', { name: 'Run', exact: true })).toBeEnabled()
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
      const deniedWorkflow = await createBasicWorkflowViaApi(app, deniedWorkflowName, 'Script', {
        projectId: deniedProject.id,
      })
      deniedWorkflowId = deniedWorkflow.id
      const allowedWorkflow = await createBasicWorkflowViaApi(app, allowedWorkflowName, 'Script', {
        projectId: allowedProject.id,
      })
      allowedWorkflowId = allowedWorkflow.id

      await app.route('**/api/v1/authz/can_i', async (route) => {
        const body = route.request().postDataJSON() as {
          resource_type?: string
          resource_labels?: { kind?: string }
          resource_project?: string
        }
        if (
          body.resource_type === 'step_type' &&
          body.resource_labels?.kind === 'script' &&
          body.resource_project === deniedProject.id
        ) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ allowed: false }),
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
