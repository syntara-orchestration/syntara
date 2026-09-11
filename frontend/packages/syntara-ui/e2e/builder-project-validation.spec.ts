/**
 * E2E Tests: Builder Save Validation — Project Required
 *
 * Critical paths covered:
 * - Saving a new workflow without a project keeps the user on /new and shows
 *   a danger state on the project selector (aria-invalid)
 * - Selecting a project then saving succeeds and navigates away from /new
 * - Save button is always clickable (never aria-disabled due to missing project)
 * - Project selector is disabled when editing an existing workflow (AAP-79246)
 *
 * Note: Toast notifications are intentionally NOT asserted here — they are
 * tested in unit tests and are too ephemeral for reliable E2E assertions.
 *
 * AAP-82756: The builder always clears the project selection on mount for new
 * workflows, so the project selector is deterministically empty regardless of
 * any previously persisted selection in Zustand/localStorage.
 */

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, selectProjectIfRequired } from './helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi, ensureProject } from './utils/api'

test.describe('Builder save validation — project required', () => {
  /**
   * Core validation flow: save without project → danger state on selector →
   * select project → save succeeds and navigates away.
   * AAP-82756: Project is always cleared on mount so this is deterministic.
   */
  test('saving new workflow without project shows error then succeeds after project selection', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-proj-validation')
    await ensureProject(app)

    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    // Add a trigger step
    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    // Project selector must always be empty for new workflows (AAP-82756)
    await expect(app.getByPlaceholder('Select a project')).toBeVisible()

    try {
      await app.getByPlaceholder('Workflow name').fill(workflowName)

      // Act: save without selecting a project
      await app.getByRole('button', { name: 'Save workflow' }).click()

      // Assert: URL remains at /new (save was rejected)
      await expect(app).toHaveURL(/workflow-builder\/new/, { timeout: 5_000 })

      // Assert: project selector shows aria-invalid danger state
      await expect(app.locator('[aria-invalid="true"]')).toBeVisible()

      // Act: select a project (uses helper that skips non-project options like "Create project")
      await selectProjectIfRequired(app)

      // Assert: danger state is cleared
      await expect(app.locator('[aria-invalid="true"]')).not.toBeVisible()

      // Act: save again — should succeed
      await app.getByRole('button', { name: 'Save workflow' }).click()

      // Assert: navigated away from /new to the persisted workflow URL
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
    } finally {
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const row = app.getByRole('row', { name: new RegExp(workflowName) })
      if ((await row.count()) > 0) {
        await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
        await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
        await app.getByRole('checkbox', { name: /I understand this workflow/i }).check()
        await app.getByRole('button', { name: 'Delete workflow' }).click()
      }
    }
  })

  /**
   * Verify Save button is always clickable even when no project is selected.
   * The previous behaviour disabled the button; now validation fires on click.
   */
  test('Save button is clickable even without a project selected', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    const saveButton = app.getByRole('button', { name: 'Save workflow' })
    await expect(saveButton).toBeVisible()
    await expect(saveButton).not.toHaveAttribute('aria-disabled', 'true')
  })

  /**
   * Saving a new workflow after selecting a project navigates away from /new.
   * AAP-82756: Project is always cleared on mount, so explicit selection is always required.
   */
  test('saving new workflow with project selected succeeds immediately', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-proj-save-ok')
    await ensureProject(app)

    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    try {
      // Add a trigger step
      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()

      // Select a project (always required since AAP-82756 clears on mount)
      await selectProjectIfRequired(app)

      // Name and save
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save workflow' }).click()

      // Assert: navigated away from /new — workflow was persisted
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
    } finally {
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const row = app.getByRole('row', { name: new RegExp(workflowName) })
      if ((await row.count()) > 0) {
        await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
        await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
        await app.getByRole('checkbox', { name: /I understand this workflow/i }).check()
        await app.getByRole('button', { name: 'Delete workflow' }).click()
      }
    }
  })

  /**
   * Project required error fires even when the workflow already has steps.
   * AAP-82756: No skip guard needed — project is always cleared on mount.
   */
  test('project required error fires even when workflow has steps', async ({ app }) => {
    await ensureProject(app)

    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    // Project selector must be empty (AAP-82756)
    await expect(app.getByPlaceholder('Select a project')).toBeVisible()

    // Click Save without selecting a project
    await app.getByRole('button', { name: 'Save workflow' }).click()

    // Assert: URL remains at /new (save was blocked)
    await expect(app).toHaveURL(/workflow-builder\/new/, { timeout: 5_000 })

    // Assert: project selector is in danger/invalid state
    await expect(app.locator('[aria-invalid="true"]')).toBeVisible()
  })

  /**
   * AAP-79246: project_id is immutable after creation — the project selector
   * must be disabled when editing an existing workflow.
   */
  test('project selector is disabled when editing an existing workflow', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-proj-immutable')
    const { id: workflowId } = await createWorkflowViaApi(app, workflowName, [
      { id: 'trigger', name: 'Manual trigger', type: 'manual_trigger', parameters: {} },
    ])

    try {
      await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 15_000 })

      const projectInput = app.getByRole('textbox', { name: 'Project' })
      await expect(projectInput).toBeVisible()
      await expect(projectInput).toBeDisabled()
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})
