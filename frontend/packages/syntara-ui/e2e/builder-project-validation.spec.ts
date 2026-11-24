/**
 * E2E Tests: New Workflow — Project Chosen Before the Builder Opens
 *
 * Critical paths covered:
 * - Opening /workflow-builder/new shows the "Select a project" modal instead
 *   of the canvas
 * - Continue stays disabled until a project is selected; selecting one and
 *   continuing opens the builder at /workflow-builder/new?projectId=<id>
 * - Cancel closes the modal and returns to /workflows
 * - /workflow-builder/new?projectId=<id> pre-fills the modal with that project
 * - After Continue the toolbar shows "Project: <name>" as text (no project
 *   selector) and saving persists the workflow
 * - Editing an existing workflow shows its project as text because project_id
 *   is immutable
 *
 * Note: Toast notifications are intentionally NOT asserted here — they are
 * tested in unit tests and are too ephemeral for reliable E2E assertions.
 *
 * The modal pre-fills the only project when the user has exactly one
 * non-built-in project. Tests that need an empty picker create a second
 * project first so that pre-fill cannot apply.
 */

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, clickSaveAndWait, openNewWorkflowBuilder, selectProjectDialog } from './helpers/workflows'
import {
  createProjectViaApi,
  createWorkflowViaApi,
  deleteProjectViaApi,
  deleteWorkflowViaApi,
  ensureProject,
} from './utils/api'

test.describe('New workflow — project selection modal', () => {
  test('opening a new workflow shows the project modal instead of the canvas', async ({ app }) => {
    await ensureProject(app)

    await app.goto(toAppUrl('/workflow-builder/new'))

    const dialog = selectProjectDialog(app)
    await expect(dialog).toBeVisible()
    await expect(dialog.getByLabel('Project', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Continue', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()

    // The builder is not rendered until a project is confirmed
    await expect(app.getByRole('heading', { name: 'Select a trigger step' })).not.toBeVisible()
    await expect(app.getByPlaceholder('Workflow name')).not.toBeVisible()
  })

  test('Continue is disabled until a project is selected', async ({ app }) => {
    await ensureProject(app)
    // A second project rules out the single-project pre-fill
    const projectName = buildUniqueName('e2e-proj-modal')
    const { id: projectId } = await createProjectViaApi(app, projectName)

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      const dialog = selectProjectDialog(app)
      await expect(dialog).toBeVisible()

      const continueButton = dialog.getByRole('button', { name: 'Continue', exact: true })
      await expect(continueButton).toBeDisabled()

      // Act: pick the project from the typeahead
      const projectInput = dialog.getByLabel('Project', { exact: true })
      await projectInput.click()
      await projectInput.fill(projectName)
      await app.getByRole('option', { name: new RegExp(`^${projectName}(\\s|$)`) }).click()

      // Assert: Continue is enabled and opens the builder for that project
      await expect(continueButton).toBeEnabled()
      await continueButton.click()

      await expect(dialog).not.toBeVisible()
      await expect(app).toHaveURL(new RegExp(`/workflow-builder/new\\?(?:.*&)?projectId=${projectId}`))
      await expect(app.getByRole('heading', { name: 'Select a trigger step' })).toBeVisible()
      await expect(app.getByText(`Project: ${projectName}`, { exact: true })).toBeVisible()
    } finally {
      await deleteProjectViaApi(app, projectId)
    }
  })

  test('Cancel returns to the workflows list', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    const dialog = selectProjectDialog(app)
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()

    await expect(app).toHaveURL(/\/workflows$/)
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
    await expect(dialog).not.toBeVisible()
  })

  /**
   * ?projectId pre-fills the modal; after Continue the toolbar shows the
   * project as text and saving persists the workflow in that project.
   */
  test('projectId in the URL pre-fills the modal and the workflow saves into that project', async ({ app }) => {
    await ensureProject(app)
    const projectName = buildUniqueName('e2e-proj-prefill')
    const { id: projectId } = await createProjectViaApi(app, projectName)
    const workflowName = buildUniqueName('e2e-proj-save-ok')
    let workflowId: string | undefined

    try {
      await app.goto(toAppUrl(`/workflow-builder/new?projectId=${projectId}`))
      const dialog = selectProjectDialog(app)
      await expect(dialog).toBeVisible()

      // Assert: pre-filled — the user still confirms with Continue
      await expect(dialog.getByLabel('Project', { exact: true })).toHaveValue(projectName)
      const continueButton = dialog.getByRole('button', { name: 'Continue', exact: true })
      await expect(continueButton).toBeEnabled()
      await continueButton.click()

      await expect(dialog).not.toBeVisible()
      await expect(app).toHaveURL(new RegExp(`/workflow-builder/new\\?(?:.*&)?projectId=${projectId}`))
      await expect(app.getByRole('heading', { name: 'Select a trigger step' })).toBeVisible()

      // Assert: the toolbar shows the project as text, with no selector
      await expect(app.getByText(`Project: ${projectName}`, { exact: true })).toBeVisible()
      await expect(app.getByRole('textbox', { name: 'Project', exact: true })).toHaveCount(0)

      // Act: add a trigger, name and save
      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create', exact: true }).click()
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await clickSaveAndWait(app)

      // Assert: persisted — navigated away from /new, project unchanged
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
      workflowId = new URL(app.url()).pathname.split('/').pop()
      await expect(app.getByText(`Project: ${projectName}`, { exact: true })).toBeVisible()
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
      await deleteProjectViaApi(app, projectId)
    }
  })

  test('openNewWorkflowBuilder helper lands in the builder with the chosen project', async ({ app }) => {
    const project = await ensureProject(app)
    expect(project, 'ensureProject must return the default project').not.toBeNull()
    const projectName = project?.name ?? 'default'

    await openNewWorkflowBuilder(app, { projectName })

    await expect(app.getByRole('heading', { name: 'Select a trigger step' })).toBeVisible()
    await expect(app.getByText(`Project: ${projectName}`, { exact: true })).toBeVisible()
  })

  /**
   * project_id is immutable after creation, so the editor shows the project
   * as text.
   */
  test('editing an existing workflow shows its project as text, not a selector', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-proj-immutable')
    const project = await ensureProject(app)
    const { id: workflowId } = await createWorkflowViaApi({
      app,
      name: workflowName,
      triggers: [{ id: 'trigger', name: 'Manual trigger', type: 'manual_trigger', parameters: {} }],
    })

    try {
      await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 15_000 })

      await expect(app.getByText(`Project: ${project?.name ?? 'default'}`, { exact: true })).toBeVisible()
      await expect(app.getByRole('textbox', { name: 'Project', exact: true })).toHaveCount(0)
      await expect(app.getByRole('combobox', { name: 'Project', exact: true })).toHaveCount(0)
      await expect(selectProjectDialog(app)).toHaveCount(0)
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})
