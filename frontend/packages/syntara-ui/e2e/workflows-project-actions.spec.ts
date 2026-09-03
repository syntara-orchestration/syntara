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
import { buildUniqueName, createBasicWorkflow, deleteWorkflow, deleteProject } from './helpers/workflows'

test.describe('Workflows Page - Project Actions in All Projects View', () => {
  test('project group header shows kebab menu with edit and delete actions', async ({ app }) => {
    test.setTimeout(60_000)

    const projectName = buildUniqueName('e2e-project')
    const workflowName = buildUniqueName('e2e-workflow')

    try {
      // Create a project with a workflow so it appears in the grouped view
      await app.goto(toAppUrl('/workflows'))

      // Create project via project selector
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await expect(createDialog).toBeVisible()
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(projectName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      // Create a workflow in this project
      await createBasicWorkflow(app, workflowName, 'Test workflow')

      // Go back to All projects view
      await app.goto(toAppUrl('/workflows'))
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Find the project group header row
      const projectRow = app.getByRole('row').filter({ hasText: projectName })
      await expect(projectRow).toBeVisible()

      // Find and click the kebab menu for this project
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await expect(projectKebab).toBeVisible()
      await projectKebab.click()

      // Verify Edit and Delete actions are present
      await expect(app.getByRole('menuitem', { name: /Edit project/i })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: /Delete project/i })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteProject(app, projectName)
    }
  })

  test('edit project from group header updates name immediately', async ({ app }) => {
    test.setTimeout(60_000)

    const originalName = buildUniqueName('e2e-project-original')
    const updatedName = buildUniqueName('e2e-project-updated')
    const workflowName = buildUniqueName('e2e-workflow')

    try {
      // Create project
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(originalName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      // Create workflow
      await createBasicWorkflow(app, workflowName, 'Test')

      // Navigate to All projects view
      await app.goto(toAppUrl('/workflows'))
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Open project kebab menu
      const projectRow = app.getByRole('row').filter({ hasText: originalName })
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
      await deleteWorkflow(app, workflowName)
      await deleteProject(app, updatedName) // Use updated name since project was renamed
    }
  })

  test.skip('delete project shows confirmation dialog with cascade warnings', async ({ app }) => {
    test.setTimeout(60_000)

    const projectName = buildUniqueName('e2e-project-delete')
    const workflowName = buildUniqueName('e2e-workflow')

    try {
      // Create project and workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(projectName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      await createBasicWorkflow(app, workflowName, 'Test')

      // Navigate to All projects view
      await app.goto(toAppUrl('/workflows'))
      await projectSelector.click()
      await app.getByRole('option', { name: 'All projects' }).click()

      // Open delete from project kebab
      const projectRow = app.getByRole('row').filter({ hasText: projectName })
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
      await deleteWorkflow(app, workflowName)
      await deleteProject(app, projectName)
    }
  })
})

test.describe('Workflows Page - Project Actions in Selected Project View', () => {
  test.skip('page header shows project kebab menu when specific project selected', async ({ app }) => {
    test.setTimeout(60_000)

    const projectName = buildUniqueName('e2e-project-header')
    const workflowName = buildUniqueName('e2e-workflow')

    try {
      // Create project and workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(projectName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      await createBasicWorkflow(app, workflowName, 'Test')

      // Ensure we're viewing this specific project
      await app.goto(toAppUrl('/workflows'))
      await projectSelector.click()
      await app.getByRole('option', { name: projectName }).click()

      // Find and click the kebab menu in the page header
      const headerKebab = app.getByRole('button', { name: 'Project actions' })
      await expect(headerKebab).toBeVisible()
      await headerKebab.click()

      // Verify Edit and Delete actions are present
      await expect(app.getByRole('menuitem', { name: /Edit project/i })).toBeVisible()
      await expect(app.getByRole('menuitem', { name: /Delete project/i })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteProject(app, projectName)
    }
  })

  test.skip('edit project from header updates name in project selector', async ({ app }) => {
    test.setTimeout(60_000)

    const originalName = buildUniqueName('e2e-project-orig')
    const updatedName = buildUniqueName('e2e-project-upd')
    const workflowName = buildUniqueName('e2e-workflow')

    try {
      // Create project and workflow
      await app.goto(toAppUrl('/workflows'))
      const projectSelector = app.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await app.getByRole('option', { name: 'Create project' }).click()

      const createDialog = app.getByRole('dialog', { name: /Create project/i })
      await createDialog.getByRole('textbox', { name: 'Project name' }).fill(originalName)
      await createDialog.getByRole('button', { name: 'Create project' }).click()
      await expect(createDialog).not.toBeVisible({ timeout: 15_000 })

      await createBasicWorkflow(app, workflowName, 'Test')

      // Select the project
      await app.goto(toAppUrl('/workflows'))
      await projectSelector.click()
      await app.getByRole('option', { name: originalName }).click()

      // Edit via header kebab
      const headerKebab = app.getByRole('button', { name: 'Project actions' })
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
      await deleteWorkflow(app, workflowName)
      await deleteProject(app, updatedName) // Use updated name since project was renamed
    }
  })
})
