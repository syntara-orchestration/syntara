/**
 * E2E Tests: Builder toolbar buttons disabled while node editor is open
 *
 * Critical paths covered:
 * - Save, Run, and Publish buttons are disabled when a node editor panel is open
 * - Buttons re-enable after closing the node editor
 * - Tooltips show the correct "finish editing" message when disabled
 */

import { type Page, test, expect } from './fixtures'
import {
  buildUniqueName,
  closeNodeEditorPanel,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  deleteWorkflow,
} from './helpers/workflows'

/** Reset layout and fit view so all nodes are in the viewport (required in CI). */
async function layoutCanvas(app: Page) {
  const layoutButton = app.getByRole('button', { name: 'Reset layout', exact: true })
  if ((await layoutButton.count()) > 0) {
    await layoutButton.click()
    await app.waitForSelector('[role="group"][aria-roledescription="node"]', { state: 'visible', timeout: 5_000 })
  }
  const fitViewButton = app.getByRole('button', { name: 'Fit view' })
  if ((await fitViewButton.count()) > 0) {
    await fitViewButton.click()
  }
}

/** Click a React Flow node by its visible text label to open its editor. */
async function clickNode(app: Page, nodeText: string) {
  await layoutCanvas(app)
  const node = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeText })
  await expect(node).toBeVisible({ timeout: 5_000 })
  await node.click()
}

test.describe('builder toolbar disabled while editing', () => {
  test('Save, Run, and Publish are disabled when a node editor is open', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-toolbar-disabled')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Toolbar test action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      // Mark dirty so Save would normally be enabled
      await app.getByPlaceholder('Workflow name').fill(`${workflowName}-dirty`)

      // Verify Save is initially enabled (aria-disabled=false or absent)
      const saveBtn = app.getByRole('button', { name: 'Save', exact: true })
      await expect(saveBtn).not.toHaveAttribute('aria-disabled', 'true')

      // Click a node to open the editor panel
      await clickNode(app, 'Toolbar test action')

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

      // Click a node to open the editor
      await clickNode(app, 'Tooltip test action')
      const cancelBtn = app.getByRole('button', { name: 'Cancel without saving' })
      await expect(cancelBtn).toBeVisible({ timeout: 10_000 })

      // Hover Save to trigger tooltip
      const saveBtn = app.getByRole('button', { name: 'Save', exact: true })
      await saveBtn.hover()

      // Tooltip should contain "finish editing" message
      await expect(app.getByRole('tooltip')).toContainText('Finish editing the current step before saving')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
