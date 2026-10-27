/**
 * E2E Tests (AAP-72719): Workflow Builder - Auto-Save on Enable and Run
 *
 * Objective: Verify that the workflow auto-saves when the user enables or runs it.
 *
 * Test coverage:
 * - Workflow auto-saves and persists changes (including multiple nodes) when clicking Run
 * - Confirmation dialog shows "Run now" when workflow is already saved
 * - Canceling run dialog preserves dirty state
 */

import { test, expect, toAppUrl } from '../fixtures'
import {
  buildUniqueName,
  deleteWorkflow,
  closeStepEditorPanel,
  createWorkflowWithTrigger,
  addScriptStep,
} from '../helpers/workflows'

test('workflow auto-saves when clicking Run with unsaved changes', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-autosave')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeStepEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Make changes to the workflow (add multiple nodes to verify complex state)
    await addScriptStep(app, 'Auto-Save Test 1', 'print("auto-save-1")')
    await addScriptStep(app, 'Auto-Save Test 2', 'print("auto-save-2")')

    // Verify the nodes are added (workflow is now dirty)
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Auto-Save Test 1' })
    ).toBeVisible()
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Auto-Save Test 2' })
    ).toBeVisible()

    // Click the Run button without manually saving
    const runButton = app.getByRole('button', { name: 'Run' })
    await expect(runButton).toBeVisible()
    await runButton.click()

    // Verify confirmation dialog appears
    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Verify dialog mentions saving (shows "Save and run" for dirty workflow)
    await expect(dialog).toContainText(/save.*run|saving|unsaved changes/i)

    // Verify the confirm button says "Save and run" (not just "Run now")
    const confirmButton = dialog.getByRole('button', { name: /save.*run/i })
    await expect(confirmButton).toBeVisible()

    // Click "Save and run" to confirm
    await confirmButton.click()

    // Wait for dialog to close (execution starting)
    await expect(dialog).not.toBeVisible({ timeout: 10000 })

    // After running, the builder navigates to the execution detail page
    await expect(app).toHaveURL(/\/executions\//, { timeout: 15000 })

    // Navigate to the workflows list
    await app.getByRole('link', { name: 'Workflows' }).click()
    await expect(app).toHaveURL(toAppUrl('/workflows'), { timeout: 10000 })

    // Re-open the workflow to verify changes WERE saved
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()

    // Wait for builder to load
    await expect(app).toHaveURL(/workflow-builder/)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Verify both auto-saved nodes are present
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Auto-Save Test 1' })
    ).toBeVisible()
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Auto-Save Test 2' })
    ).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('run confirmation shows "Run now" when workflow has no unsaved changes', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-autosave')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeStepEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Do NOT make changes - workflow is already saved

    // Click the Run button
    const runButton = app.getByRole('button', { name: 'Run' })
    await expect(runButton).toBeVisible()
    await runButton.click()

    // Verify confirmation dialog appears
    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Verify the confirm button says "Run now" (not "Save and run")
    const confirmButton = dialog.getByRole('button', { name: 'Run now' })
    await expect(confirmButton).toBeVisible()

    // Verify dialog does not mention unsaved changes
    await expect(dialog).not.toContainText(/unsaved/i)

    // Close the dialog (we don't need to actually run it)
    const cancelButton = dialog.getByRole('button', { name: 'Cancel' })
    await cancelButton.click()

    await expect(dialog).not.toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('canceling run dialog with unsaved changes keeps workflow dirty', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-autosave')
  await createWorkflowWithTrigger(app, workflowName)

  try {
    await closeStepEditorPanel(app)
    await expect(app.getByText('Manual trigger')).toBeVisible()

    // Make changes
    await addScriptStep(app, 'Cancel Run Test', 'print("cancel")')
    await expect(
      app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Cancel Run Test' })
    ).toBeVisible()

    // Click Run
    const runButton = app.getByRole('button', { name: 'Run' })
    await runButton.click()

    // Wait for confirmation dialog
    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Click Cancel (don't save and run)
    const cancelButton = dialog.getByRole('button', { name: 'Cancel' })
    await cancelButton.click()

    await expect(dialog).not.toBeVisible()

    // Try to navigate away - should see unsaved changes prompt
    await app.getByRole('link', { name: 'Workflows' }).click()

    // Scope dialog by content to avoid strict mode violations
    const navDialog = app.getByRole('dialog').filter({ hasText: /save changes before exiting/i })
    await expect(navDialog).toBeVisible()

    // Verify unsaved changes dialog appeared (workflow is still dirty)
    await expect(navDialog).toContainText(/save|exit without saving/i)

    // Cancel navigation to stay in builder
    await navDialog.getByRole('button', { name: 'Cancel' }).click()

    await expect(navDialog).not.toBeVisible()
    await expect(app).toHaveURL(/workflow-builder/)
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})
