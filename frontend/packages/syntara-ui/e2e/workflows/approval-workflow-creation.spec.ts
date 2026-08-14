import { type Page } from '../fixtures'
import { test, expect, toAppUrl } from '../fixtures'
import { addApprovalNode, addManualTrigger } from '../helpers/v2-nodes'
import {
  addNodePanel,
  waitForUIReady,
  buildUniqueName,
  fillCodeEditor,
  closeNodeEditorPanel,
} from '../helpers/workflows'
import { apiRequest } from '../utils/api'

/** Select a category then a subtype within the add-node panel. */
async function selectCategoryAndType(page: Page, category: string, subtype: string) {
  const panel = addNodePanel(page)
  await panel.getByRole('button', { name: category, exact: true }).click()
  const subtypeBtn = panel.getByRole('button', { name: subtype, exact: true })
  await expect(subtypeBtn).toBeVisible({ timeout: 5_000 })
  await subtypeBtn.click()
}

/**
 * E2E test for creating an approval workflow from scratch using canvas interactions.
 *
 * This test builds a complete workflow:
 * - Manual Trigger
 * - Approval Node
 * - Script Node (on approved path)
 * - Script Node (on rejected path) - optional for valid workflow
 *
 * Uses real user interactions on the canvas to add nodes and configure them.
 * All tests are self-contained with try-finally cleanup.
 */
test.describe('Approval Workflow Creation', () => {
  test('create workflow with trigger, approval node, and script on approved path', async ({ app }) => {
    const workflowName = buildUniqueName('E2E Approval Workflow')
    let workflowId: string | undefined

    try {
      // Step 1: Navigate to workflow builder (new workflow)
      await app.goto(toAppUrl('/workflow-builder/new'))

      // Step 2: Add Manual Trigger
      await addManualTrigger(app, 'Manual Start')

      // Wait for canvas to be ready
      await expect(app.getByText('Manual Start')).toBeVisible({ timeout: 10_000 })

      // Step 3: Add Approval node
      await addApprovalNode(app, 'Deployment Approval')

      // Wait for approval node to appear on canvas
      await expect(app.getByText('Deployment Approval')).toBeVisible({ timeout: 10_000 })

      // Step 4: Add script on approved path
      // Click layout to reveal branch buttons
      // eslint-disable-next-line no-restricted-properties -- Layout button selector matches multiple in React Flow toolbar, .first() is correct here
      const layoutButton = app.getByRole('button', { name: 'Layout' }).first()
      await expect(layoutButton).toBeVisible({ timeout: 10_000 })
      await layoutButton.click()

      // Wait for UI to stabilize after layout
      await waitForUIReady(app)

      // Click the "Approved" branch button
      const approvedButton = app.getByTestId('add-node-button-approved')
      await expect(approvedButton).toBeVisible({ timeout: 10_000 })
      await approvedButton.click()

      // Panel opens on the approved branch — use it directly without re-opening
      await expect(addNodePanel(app)).toHaveCount(1)
      await selectCategoryAndType(app, 'Action', 'Script')

      const nameInput = app.getByRole('textbox', { name: 'Name', exact: true })
      await expect(nameInput).toBeVisible({ timeout: 10_000 })
      await expect(nameInput).toBeEditable({ timeout: 5_000 })
      await nameInput.fill('Deploy to Production')
      await fillCodeEditor(app, { value: 'print("Deploying to production...")' })
      await app.getByRole('button', { name: 'Create', exact: true }).click()
      await closeNodeEditorPanel(app)

      // Wait for script node to appear
      await expect(app.getByText('Deploy to Production')).toBeVisible({ timeout: 10_000 })

      // Step 5: (Optional) Add script on rejected path
      await layoutButton.click()
      await waitForUIReady(app)

      const rejectedButton = app.getByTestId('add-node-button-rejected')
      const hasRejectedButton = await rejectedButton.isVisible().catch(() => false)

      if (hasRejectedButton) {
        await rejectedButton.click()

        // Panel opens on the rejected branch — use it directly
        await expect(addNodePanel(app)).toHaveCount(1)
        await selectCategoryAndType(app, 'Action', 'Script')

        const rollbackNameInput = app.getByRole('textbox', { name: 'Name', exact: true })
        await expect(rollbackNameInput).toBeVisible({ timeout: 10_000 })
        await expect(rollbackNameInput).toBeEditable({ timeout: 5_000 })
        await rollbackNameInput.fill('Rollback Changes')
        await fillCodeEditor(app, { value: 'print("Rolling back changes...")' })
        await app.getByRole('button', { name: 'Create', exact: true }).click()
        await closeNodeEditorPanel(app)

        await expect(app.getByText('Rollback Changes')).toBeVisible({ timeout: 10_000 })
      }

      // Step 6: Save the workflow
      const workflowNameInput = app.getByPlaceholder('Workflow name')
      await expect(workflowNameInput).toBeVisible()
      await workflowNameInput.fill(workflowName)

      const saveWorkflowButton = app.getByRole('button', { name: 'Save' })
      await expect(saveWorkflowButton).toBeVisible()
      await saveWorkflowButton.click()

      // Step 7: Verify workflow was saved (URL changes to /workflow-builder/{id})
      await expect(app).toHaveURL(/\/workflow-builder\/[^/]+/, { timeout: 15_000 })

      // Extract workflow ID from URL for cleanup
      workflowId = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]

      // Step 8: Verify all nodes are visible on the saved workflow
      await expect(app.getByText('Manual Start')).toBeVisible()
      await expect(app.getByText('Deployment Approval')).toBeVisible()
      await expect(app.getByText('Deploy to Production')).toBeVisible()

      // Step 9: Verify the workflow can be found in the workflows list
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const workflowsTable = app.getByRole('grid', { name: 'Workflows table' })
      await expect(workflowsTable).toBeVisible()

      // Search for our workflow by name
      const searchInput = app.getByPlaceholder('Filter by name')
      await searchInput.fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Verify workflow appears in the list
      await expect(app.getByText(workflowName)).toBeVisible({ timeout: 10_000 })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})
