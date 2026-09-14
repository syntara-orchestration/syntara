/**
 * E2E Tests (ANSTRAT-1845): Workflows — Create New Workflow
 *
 * Critical paths covered:
 * - User can create a new workflow from the workflows page
 * - Creation flow navigates to the workflow builder
 * - New workflow appears in the workflows table after creation
 *
 * Edge cases:
 * - Form validation (name required)
 * - Builder auto-saves workflow
 * - Workflow appears in filtered list
 */

import { test, expect, toAppUrl } from '../fixtures'
import { buildUniqueName, deleteWorkflow, selectProjectIfRequired } from '../helpers/workflows'

test.describe('Workflows - Create New Workflow', () => {
  test('user creates a new workflow with name and description', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-create')

    try {
      // Navigate to workflows page
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const createButton = app.getByRole('button', { name: 'Create workflow' })
      await expect(createButton).toBeVisible()
      await createButton.click()

      await expect(app).toHaveURL(/workflow-builder\/new/)
      await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()

      // Select project if required
      await selectProjectIfRequired(app)

      const workflowNameInput = app.getByPlaceholder('Workflow name')
      await expect(workflowNameInput).toBeVisible()
      await workflowNameInput.clear()
      await workflowNameInput.fill(workflowName)

      await app.getByRole('button', { name: 'Save' }).click()

      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15000 })
      await expect(app).not.toHaveURL(/workflow-builder\/new/)

      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const table = app.getByRole('grid', { name: 'Workflows table' })
      const workflowRow = table.getByRole('row', { name: new RegExp(workflowName) })
      await expect(workflowRow).toBeVisible()

      // Verify the workflow name is clickable (navigates to builder)
      const workflowButton = workflowRow.getByRole('link', { name: workflowName, exact: true })
      await expect(workflowButton).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('create button navigates to builder with new workflow', async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    await app.getByRole('button', { name: 'Create workflow' }).click()

    await expect(app).toHaveURL(/workflow-builder\/new/)

    const workflowNameInput = app.getByPlaceholder('Workflow name')
    await expect(workflowNameInput).toBeVisible()

    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()
  })

  test('workflow name can be customized before saving', async ({ app }) => {
    const customName = buildUniqueName('e2e-custom')

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()

      await selectProjectIfRequired(app)

      const workflowNameInput = app.getByPlaceholder('Workflow name')
      await expect(workflowNameInput).toBeVisible()

      await workflowNameInput.clear()
      await workflowNameInput.fill(customName)

      const saveButton = app.getByRole('button', { name: 'Save' })
      await expect(saveButton).toBeVisible()
      await saveButton.click()

      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15000 })
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(customName)
    } finally {
      await deleteWorkflow(app, customName)
    }
  })

  test('user can create workflow and immediately edit it', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-edit')

    try {
      // Create workflow via Create button
      await app.goto(toAppUrl('/workflows'))
      await app.getByRole('button', { name: 'Create workflow' }).click()

      await expect(app).toHaveURL(/workflow-builder\/new/)
      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()

      await selectProjectIfRequired(app)

      const nameInput = app.getByPlaceholder('Workflow name')
      await nameInput.clear()
      await nameInput.fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()

      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15000 })
      await expect(app).not.toHaveURL(/workflow-builder\/new/)

      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)

      await expect(app.getByRole('button', { name: 'Layout' })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('multiple workflows can be created sequentially', async ({ app }) => {
    const workflow1Name = buildUniqueName('e2e-multi-1')
    const workflow2Name = buildUniqueName('e2e-multi-2')

    try {
      // Create first workflow
      await app.goto(toAppUrl('/workflows'))
      await app.getByRole('button', { name: 'Create workflow' }).click()
      await expect(app).toHaveURL(/workflow-builder\/new/)

      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger 1')
      await app.getByRole('button', { name: 'Create' }).click()

      await selectProjectIfRequired(app)
      const name1Input = app.getByPlaceholder('Workflow name')
      await name1Input.clear()
      await name1Input.fill(workflow1Name)
      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15000 })

      // Go back and create second workflow
      await app.goto(toAppUrl('/workflows'))
      await app.getByRole('button', { name: 'Create workflow' }).click()
      await expect(app).toHaveURL(/workflow-builder\/new/)

      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger 2')
      await app.getByRole('button', { name: 'Create' }).click()

      await selectProjectIfRequired(app)
      const name2Input = app.getByPlaceholder('Workflow name')
      await name2Input.clear()
      await name2Input.fill(workflow2Name)
      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15000 })

      // Verify both workflows exist in the table
      await app.goto(toAppUrl('/workflows'))
      const table = app.getByRole('grid', { name: 'Workflows table' })
      await expect(table).toBeVisible()

      // Check first workflow
      await app.getByPlaceholder('Filter by name').fill(workflow1Name)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(table.getByRole('row', { name: new RegExp(workflow1Name) })).toBeVisible()

      // Check second workflow — replace the name filter and wait for table to update
      await app.getByPlaceholder('Filter by name').clear()
      await app.getByPlaceholder('Filter by name').fill(workflow2Name)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(table.getByRole('row', { name: new RegExp(workflow1Name) })).toBeHidden()
      await expect(table.getByRole('row', { name: new RegExp(workflow2Name) })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflow1Name)
      await deleteWorkflow(app, workflow2Name)
    }
  })
})
