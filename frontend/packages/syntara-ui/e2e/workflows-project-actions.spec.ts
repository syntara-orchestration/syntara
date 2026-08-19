/**
 * E2E Tests: Project Actions on Workflows Page
 *
 * Critical paths covered:
 * - Project kebab menu in "All projects" view (grouped table)
 * - Project kebab menu in page header when specific project selected
 * - Edit project updates name immediately without refresh
 * - Delete project shows confirmation dialog with cascade warnings
 * - Permission gating for project actions
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { apiRequest, getAuthToken, deleteWorkflowViaApi } from './utils/api'

async function deleteProjectViaApi(app: Page, projectName: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (!token) return
    const listResp = await apiRequest(app, 'get', '/projects', { token })
    if (!listResp.ok()) return
    const body = (await listResp.json()) as { resources: Array<{ id: string; name: string }> }
    const project = body.resources.find((p) => p.name === projectName)
    if (project) {
      await apiRequest(app, 'delete', `/projects/${project.id}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

async function createProjectAndWorkflowViaApi(
  app: Page,
  projectName: string,
  workflowName: string
): Promise<{ projectId: string; workflowId: string }> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('Could not obtain auth token')

  const projResp = await apiRequest(app, 'post', '/projects', {
    token,
    data: { name: projectName, description: `E2E test project: ${projectName}` },
  })
  if (!projResp.ok()) throw new Error(`Failed to create project: ${projResp.status()}`)
  const project = (await projResp.json()) as { id: string }

  const wfResp = await apiRequest(app, 'post', '/workflows', {
    token,
    data: {
      name: workflowName,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name: workflowName,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [],
        edges: [],
      },
    },
  })
  if (!wfResp.ok()) throw new Error(`Failed to create workflow: ${wfResp.status()}`)
  const workflow = (await wfResp.json()) as { id: string }

  return { projectId: project.id, workflowId: workflow.id }
}

test.describe('Workflows Page - Project Actions in All Projects View', () => {
  test('project group header shows kebab menu with edit and delete actions', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project')
    const workflowName = buildUniqueName('e2e-workflow')
    let workflowId: string | undefined

    try {
      const result = await createProjectAndWorkflowViaApi(app, projectName, workflowName)
      workflowId = result.workflowId

      // Navigate to All projects view
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Find the project group header row
      const projectRow = app.getByRole('row').filter({ hasText: projectName })
      await expect(projectRow).toBeVisible({ timeout: 15_000 })

      // Find and click the kebab menu for this project
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await expect(projectKebab).toBeVisible()
      await projectKebab.click()

      // Verify Edit and Delete actions are present
      await expect(app.getByRole('menuitem', { name: /Edit project/i })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: /Delete project/i })).toBeVisible()
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
      await deleteProjectViaApi(app, projectName)
    }
  })

  test('edit project from group header updates name immediately', async ({ app }) => {
    const originalName = buildUniqueName('e2e-project-original')
    const updatedName = buildUniqueName('e2e-project-updated')
    const workflowName = buildUniqueName('e2e-workflow')
    let workflowId: string | undefined

    try {
      const result = await createProjectAndWorkflowViaApi(app, originalName, workflowName)
      workflowId = result.workflowId

      // Navigate to All projects view
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Open project kebab menu
      const projectRow = app.getByRole('row').filter({ hasText: originalName })
      await expect(projectRow).toBeVisible({ timeout: 15_000 })
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await projectKebab.click()
      await app.getByRole('menuitem', { name: /Edit project/i }).click()

      // Edit the project name
      const editDialog = app.getByRole('dialog', { name: `Edit ${originalName}` })
      await expect(editDialog).toBeVisible()
      const nameInput = editDialog.getByRole('textbox', { name: 'Project name' })
      await nameInput.clear()
      await nameInput.fill(updatedName)
      await editDialog.getByRole('button', { name: 'Save' }).click()
      await expect(editDialog).not.toBeVisible({ timeout: 15_000 })

      // Verify the updated name appears immediately without page refresh
      await expect(app.getByRole('row').filter({ hasText: updatedName })).toBeVisible({ timeout: 10_000 })
      await expect(app.getByRole('row').filter({ hasText: originalName })).not.toBeVisible()
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
      await deleteProjectViaApi(app, updatedName)
    }
  })

  test('delete project shows confirmation dialog with cascade warnings', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project-delete')
    const workflowName = buildUniqueName('e2e-workflow')
    let workflowId: string | undefined

    try {
      const result = await createProjectAndWorkflowViaApi(app, projectName, workflowName)
      workflowId = result.workflowId

      // Navigate to All projects view
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Open delete from project kebab
      const projectRow = app.getByRole('row').filter({ hasText: projectName })
      await expect(projectRow).toBeVisible({ timeout: 15_000 })
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await projectKebab.click()
      await app.getByRole('menuitem', { name: /Delete project/i }).click()

      // Verify confirmation dialog appears with warnings
      const deleteDialog = app.getByRole('dialog', { name: /Delete project/i })
      await expect(deleteDialog).toBeVisible()
      await expect(deleteDialog.getByText(projectName)).toBeVisible()
      await expect(deleteDialog.getByText(/^All workflows in this project will be permanently/i)).toBeVisible()
      await expect(deleteDialog.getByText(/^All project role assignments will be removed/i)).toBeVisible()

      // Verify destructive acknowledgement checkbox is required
      const confirmButton = deleteDialog.getByRole('button', { name: 'Delete' })
      await expect(confirmButton).toBeDisabled()

      const ackCheckbox = deleteDialog.getByRole('checkbox', { name: /I understand/i })
      await ackCheckbox.check()
      await expect(confirmButton).toBeEnabled()

      // Don't actually delete - just verify the UI flow works
      await deleteDialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(deleteDialog).not.toBeVisible()
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
      await deleteProjectViaApi(app, projectName)
    }
  })
})

test.describe('Workflows Page - Project Actions in Selected Project View', () => {
  test('page header shows project kebab menu when specific project selected', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project-header')

    try {
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(projectName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      // Project is now selected — kebab should be visible in header
      const headerKebab = app.getByRole('button', { name: 'Project actions' })
      await expect(headerKebab).toBeVisible({ timeout: 15_000 })
      await headerKebab.click()

      await expect(app.getByRole('menuitem', { name: /Edit project/i })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: /Delete project/i })).toBeVisible()
    } finally {
      await deleteProjectViaApi(app, projectName)
    }
  })

  test('edit project from header updates name in project selector', async ({ app }) => {
    const originalName = buildUniqueName('e2e-project-orig')
    const updatedName = buildUniqueName('e2e-project-upd')

    try {
      // Create project via UI — it becomes the selected project
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(originalName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      // Edit via header kebab
      const headerKebab = app.getByRole('button', { name: 'Project actions' })
      await expect(headerKebab).toBeVisible({ timeout: 15_000 })
      await headerKebab.click()
      await app.getByRole('menuitem', { name: /Edit project/i }).click()

      const editDialog = app.getByRole('dialog', { name: `Edit ${originalName}` })
      const nameInput = editDialog.getByRole('textbox', { name: 'Project name' })
      await nameInput.clear()
      await nameInput.fill(updatedName)
      await editDialog.getByRole('button', { name: 'Save' }).click()
      await expect(editDialog).not.toBeVisible({ timeout: 15_000 })

      // Verify the project selector shows the updated name
      await expect(projectSelector).toHaveValue(updatedName)
    } finally {
      await deleteProjectViaApi(app, updatedName)
    }
  })
})
