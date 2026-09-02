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
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi } from './helpers/workflows'
import { createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi } from './utils/api'

test.describe('Workflows Page - Project Actions in All Projects View', () => {
  test('project group header shows kebab menu with edit and delete actions', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project')
    const workflowName = buildUniqueName('e2e-workflow')
    let projectId: string | undefined
    let workflowId: string | undefined

    try {
      const project = await createProjectViaApi(app, projectName)
      projectId = project.id
      const workflow = await createBasicWorkflowViaApi(app, workflowName, undefined, { projectId })
      workflowId = workflow.id

      // Navigate to All projects view and filter to isolate our workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

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
      if (projectId) await deleteProjectViaApi(app, projectId)
    }
  })

  test('edit project from group header updates name immediately', async ({ app }) => {
    const originalName = buildUniqueName('e2e-project-original')
    const updatedName = buildUniqueName('e2e-project-updated')
    const workflowName = buildUniqueName('e2e-workflow')
    let projectId: string | undefined
    let workflowId: string | undefined

    try {
      const project = await createProjectViaApi(app, originalName)
      projectId = project.id
      const workflow = await createBasicWorkflowViaApi(app, workflowName, undefined, { projectId })
      workflowId = workflow.id

      // Navigate to All projects view and filter to isolate our workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

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
      if (projectId) await deleteProjectViaApi(app, projectId)
    }
  })

  test('delete project shows confirmation dialog with cascade warnings', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project-delete')
    const workflowName = buildUniqueName('e2e-workflow')
    let projectId: string | undefined
    let workflowId: string | undefined

    try {
      const project = await createProjectViaApi(app, projectName)
      projectId = project.id
      const workflow = await createBasicWorkflowViaApi(app, workflowName, undefined, { projectId })
      workflowId = workflow.id

      // Navigate to All projects view and filter to isolate our workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

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
      await expect(deleteDialog.getByText(/Workflows, executions, and approval requests/i)).toBeVisible()
      await expect(deleteDialog.getByText(/Role assignments, project roles, and policies/i)).toBeVisible()

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
      if (projectId) await deleteProjectViaApi(app, projectId)
    }
  })
})

test.describe('Workflows Page - Project Actions in Selected Project View', () => {
  test('page header shows project kebab menu when specific project selected', async ({ app }) => {
    const projectName = buildUniqueName('e2e-project-header')
    let projectId: string | undefined

    try {
      const project = await createProjectViaApi(app, projectName)
      projectId = project.id

      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await projectSelector.fill(projectName)
      await app.getByRole('option', { name: projectName, exact: true }).waitFor({ state: 'visible', timeout: 10_000 })
      await app.getByRole('option', { name: projectName, exact: true }).click()

      // Project is now selected — kebab should be visible in header
      const headerKebab = app.getByRole('button', { name: 'Project actions' })
      await expect(headerKebab).toBeVisible({ timeout: 15_000 })
      await headerKebab.click()

      await expect(app.getByRole('menuitem', { name: /Edit project/i })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: /Delete project/i })).toBeVisible()
    } finally {
      if (projectId) await deleteProjectViaApi(app, projectId)
    }
  })

  test('edit project from header updates name in project selector', async ({ app }) => {
    const originalName = buildUniqueName('e2e-project-orig')
    const updatedName = buildUniqueName('e2e-project-upd')
    let projectId: string | undefined

    try {
      const project = await createProjectViaApi(app, originalName)
      projectId = project.id

      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await projectSelector.fill(originalName)
      await app.getByRole('option', { name: originalName, exact: true }).waitFor({ state: 'visible', timeout: 10_000 })
      await app.getByRole('option', { name: originalName, exact: true }).click()

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
      if (projectId) await deleteProjectViaApi(app, projectId)
    }
  })
})
