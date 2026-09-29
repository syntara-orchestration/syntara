/**
 * E2E Tests: Builder toolbar buttons disabled while node editor is open
 *
 * Critical paths covered:
 * - Save, Run, and Publish buttons are disabled when a node editor panel is open
 * - Buttons re-enable after closing the node editor
 * - Tooltips show the correct "finish editing" message when disabled
 */

import { test, expect } from './fixtures'
import {
  buildUniqueName,
  closeNodeEditorPanel,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  deleteWorkflow,
  openNodeForEditing,
} from './helpers/workflows'

test.describe('builder toolbar disabled while editing', () => {
  test('Save, Run, and Publish are disabled when a node editor is open', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-toolbar-disabled')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Toolbar test action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      // Mark dirty so Save would normally be enabled
      await app.getByPlaceholder('Workflow name').fill(`${workflowName}-dirty`)

      // Verify Save is initially enabled (aria-disabled=false or absent)
      const saveBtn = app.getByRole('button', { name: 'Save workflow' })
      await expect(saveBtn).not.toHaveAttribute('aria-disabled', 'true')

      await openNodeForEditing(app, 'Toolbar test action')

      // Wait for the node editor to fully open (cancel button appears inside the panel)
      const cancelBtn = app.getByRole('button', { name: 'Cancel without saving' })
      await expect(cancelBtn).toBeVisible({ timeout: 10_000 })

      // Save should now be disabled
      await expect(saveBtn).toHaveAttribute('aria-disabled', 'true')

      // Run button should be disabled
      const runBtn = app.getByRole('button', { name: 'Run', exact: true })
      await expect(runBtn).toHaveAttribute('aria-disabled', 'true')

      // Publish workflow button should be disabled
      const publishBtn = app.getByRole('button', { name: /Publish workflow/i })
      await expect(publishBtn).toHaveAttribute('aria-disabled', 'true')

      // Close the node editor
      await closeNodeEditorPanel(app)

      // Buttons should re-enable
      await expect(saveBtn).not.toHaveAttribute('aria-disabled', 'true', { timeout: 5_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('disabled buttons show "finish editing" tooltip', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-toolbar-tooltip')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Tooltip test action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      await openNodeForEditing(app, 'Tooltip test action')
      const cancelBtn = app.getByRole('button', { name: 'Cancel without saving' })
      await expect(cancelBtn).toBeVisible({ timeout: 10_000 })

      const saveBtn = app.getByRole('button', { name: 'Save workflow' })
      await expect(saveBtn).toHaveAttribute('aria-disabled', 'true')

      // PF tooltips can lag behind hover under CI load — retry hover until visible.
      await expect(async () => {
        await saveBtn.hover()
        await expect(app.getByRole('tooltip')).toContainText('Finish editing the current step before saving')
      }).toPass({ timeout: 15_000, intervals: [500, 1_000, 2_000] })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
