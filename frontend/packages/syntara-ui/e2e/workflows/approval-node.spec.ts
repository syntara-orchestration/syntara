/**
 * E2E Tests: Approval Node Configuration [UI-13]
 *
 * Critical paths covered:
 * - Adding an Approval node to the workflow canvas
 * - Verifying approver users and approver groups fields exist
 * - Configuring message, decision window, and fallback decision fields
 * - Saving and verifying configuration persistence
 * - Reopening saved nodes to verify data persists
 *
 * Edge cases:
 * - Fallback decision options: approve, reject
 * - Decision window with different time units (hours, minutes, seconds)
 * - Message field for approval prompt text
 */

import { type Page, test, expect } from '../fixtures'
import { openAddNodePanel } from '../helpers/v2-nodes'
import {
  addNodePanel,
  buildUniqueName,
  closeNodeEditorPanel,
  deleteWorkflow,
  openNodeForEditing,
  saveAndCloseNodeForm,
  saveWorkflow,
  startWorkflowWithTrigger,
  verifyNodeVisible,
} from '../helpers/workflows'

/**
 * Helper to open the Approval node form from the add-node panel.
 * Returns after the form is visible and ready for input.
 */
async function openApprovalNodeForm(page: Page) {
  await openAddNodePanel(page)

  const panel = addNodePanel(page)
  const approvalBtn = panel.getByRole('button', { name: 'Approval', exact: true })
  await expect(approvalBtn).toBeVisible()
  await approvalBtn.click()

  // Wait for the form to load
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible()
}

/**
 * Helper to configure Approval node fields in an open form.
 */
async function configureApprovalNode(
  page: Page,
  config: {
    name?: string
    message?: string
    decisionWindowSeconds?: number
    fallbackDecision?: 'approve' | 'reject'
  }
) {
  if (config.name) {
    const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
    await expect(nameInput).toBeVisible()
    await nameInput.fill(config.name)
  }

  if (config.message) {
    const messageInput = page.getByRole('textbox', { name: 'Message' })
    await expect(messageInput).toBeVisible()
    await messageInput.fill(config.message)
  }

  if (config.decisionWindowSeconds !== undefined) {
    // Decision window uses DurationInput component with multiple fields
    // Convert seconds to appropriate units and fill
    const seconds = config.decisionWindowSeconds
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const remainingSeconds = seconds % 60

    if (hours > 0) {
      const hoursInput = page.getByLabel('Hours')
      await expect(hoursInput).toBeVisible()
      await hoursInput.fill(String(hours))
    }
    if (minutes > 0) {
      const minutesInput = page.getByLabel('Minutes')
      await expect(minutesInput).toBeVisible()
      await minutesInput.fill(String(minutes))
    }
    if (remainingSeconds > 0) {
      const secondsInput = page.getByLabel('Seconds')
      await expect(secondsInput).toBeVisible()
      await secondsInput.fill(String(remainingSeconds))
    }
  }

  if (config.fallbackDecision) {
    const enableLink = page.getByRole('button', { name: 'Enable continue on failure' })
    if ((await enableLink.count()) > 0) {
      await enableLink.click()
    }
    const fallbackToggle = page.getByRole('button', { name: 'Fallback decision', exact: true })
    await expect(fallbackToggle).toBeVisible()
    await fallbackToggle.click()
    const optionLabel = config.fallbackDecision === 'reject' ? 'Reject (default)' : 'Approve'
    await page.getByRole('option', { name: optionLabel }).click()
  }
}

/**
 * Composite helper: Add an Approval node with full configuration in one step.
 */
async function addApprovalNodeWithConfig(
  page: Page,
  config: {
    name: string
    message?: string
    decisionWindowSeconds?: number
    fallbackDecision?: 'approve' | 'reject'
  }
) {
  await openApprovalNodeForm(page)
  await configureApprovalNode(page, config)
  await saveAndCloseNodeForm(page, false, config.name)
}

test.describe('Approval Node Configuration', () => {
  test('user configures Approval node with message, decision window, and fallback decision', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-approval')

    try {
      // Arrange - Create a workflow with manual trigger
      await startWorkflowWithTrigger(app)

      // Act - Add Approval node with full configuration
      await addApprovalNodeWithConfig(app, {
        name: 'Approval step',
        message: 'Please approve this deployment to production',
        decisionWindowSeconds: 3600,
        fallbackDecision: 'reject',
      })

      // Assert - Verify the Approval node appears on canvas
      await verifyNodeVisible(app, 'Approval step')

      // Save the workflow
      await saveWorkflow(app, workflowName)

      // Assert - Verify workflow is persisted
      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)

      // Verify the node is still visible after save
      await verifyNodeVisible(app, 'Approval step')
    } finally {
      // Cleanup
      await deleteWorkflow(app, workflowName)
    }
  })

  test('user edits Approval node to verify configuration persistence', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-approval-edit')

    try {
      // Arrange - Create a workflow with an Approval node
      await startWorkflowWithTrigger(app)

      // Add Approval node with initial configuration
      await addApprovalNodeWithConfig(app, {
        name: 'Initial approval',
        message: 'Please review this change',
        decisionWindowSeconds: 7200,
        fallbackDecision: 'approve',
      })

      // Save workflow
      await saveWorkflow(app, workflowName)

      // Act - Reopen the Approval node to verify configuration persists
      await verifyNodeVisible(app, 'Initial approval')
      await openNodeForEditing(app, 'Initial approval')

      // Assert - Verify the editor panel opened and shows the persisted values
      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Initial approval')
      await expect(app.getByRole('textbox', { name: 'Message' })).toHaveValue('Please review this change')
      await expect(app.getByLabel('Hours')).toHaveValue('2')
      await expect(app.getByRole('button', { name: 'Fallback decision', exact: true })).toContainText('Approve')

      // Close the panel to verify workflow state
      // When editing (vs creating), the node details panel must close before the editor drawer
      const closeButtons = app.getByRole('button', { name: 'Close' })
      if ((await closeButtons.count()) > 1) {
        // Multiple Close buttons - close the inner panel first (node details)
        await closeButtons.last().click()
        await expect(closeButtons).toHaveCount(1, { timeout: 5000 })
      }
      await closeNodeEditorPanel(app)

      // Verify the node is still on the canvas after reopening and closing
      await verifyNodeVisible(app, 'Initial approval')
    } finally {
      // Cleanup
      await deleteWorkflow(app, workflowName)
    }
  })

  test('user configures Approval node with both fallback decision options', async ({ app }) => {
    test.slow()
    const fallbackDecisions: Array<'approve' | 'reject'> = ['approve', 'reject']
    const workflowNames: string[] = []

    try {
      // Test each fallback decision option in a separate workflow to avoid
      // non-deterministic openAddNodePanel().first() with multiple Approval nodes
      for (const decision of fallbackDecisions) {
        const workflowName = buildUniqueName(`e2e-approval-fallback-${decision}`)
        workflowNames.push(workflowName)

        // Create a fresh workflow with manual trigger
        await startWorkflowWithTrigger(app)

        // Add Approval node with specific fallback decision
        await addApprovalNodeWithConfig(app, {
          name: `Approval fallback ${decision}`,
          message: `Test ${decision} fallback`,
          decisionWindowSeconds: 600,
          fallbackDecision: decision,
        })

        // Verify the node appears on canvas
        await verifyNodeVisible(app, `Approval fallback ${decision}`)

        // Save the workflow
        await saveWorkflow(app, workflowName)

        // Assert - Verify workflow is persisted
        await expect(app).toHaveURL(/workflow-builder\/.+/)
        await verifyNodeVisible(app, `Approval fallback ${decision}`)
      }
    } finally {
      // Cleanup all created workflows
      for (const workflowName of workflowNames) {
        await deleteWorkflow(app, workflowName)
      }
    }
  })

  test('user adds Approval node, clicks to open details panel, configures, and saves', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-approval-click-edit')

    try {
      // Arrange - Create a workflow with manual trigger
      await startWorkflowWithTrigger(app)

      // Step 1: Add an Approval node to the canvas with minimal configuration
      await openApprovalNodeForm(app)
      await configureApprovalNode(app, { name: 'Approval node' })
      await saveAndCloseNodeForm(app, false, 'Approval node')

      // Step 2: Click the node to open the details panel
      await openNodeForEditing(app, 'Approval node')

      // Step 3: Configure message, decision window, and fallback decision
      await configureApprovalNode(app, {
        message: 'Please approve this deployment',
        decisionWindowSeconds: 1800,
        fallbackDecision: 'approve',
      })

      // Step 4: Save the configuration (using Update button since we're editing)
      await saveAndCloseNodeForm(app, true, 'Approval node')

      // Verify the configuration saved by reopening the node
      await openNodeForEditing(app, 'Approval node')

      // Assert - Verify all configured values are present
      await expect(app.getByRole('textbox', { name: 'Message' })).toHaveValue('Please approve this deployment')
      await expect(app.getByLabel('Minutes')).toHaveValue('30')
      await expect(app.getByRole('button', { name: 'Fallback decision', exact: true })).toContainText('Approve')

      // Close the panel
      await closeNodeEditorPanel(app)

      // Save the workflow
      await saveWorkflow(app, workflowName)
      await expect(app).toHaveURL(/workflow-builder\/.+/)
    } finally {
      // Cleanup
      await deleteWorkflow(app, workflowName)
    }
  })

  test('user verifies Parameters panel displays all Approval node fields', async ({ app }) => {
    test.slow()
    // Arrange - Create a workflow with manual trigger
    await startWorkflowWithTrigger(app)

    // Act - Open the Approval node form
    await openApprovalNodeForm(app)

    // Assert - Verify all required fields are present in the Parameters panel
    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await expect(app.getByText('Approver users')).toBeVisible()
    await expect(app.getByText('Approver groups')).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Message' })).toBeVisible()

    const fallbackToggle = app.getByRole('button', { name: 'Fallback decision', exact: true })
    await expect(fallbackToggle).toBeVisible()
    await expect(fallbackToggle).toBeDisabled()
    await expect(
      app.getByText('On failure behavior is System default (stop on failure), so this fallback will not be used.')
    ).toBeVisible()

    await app.getByRole('button', { name: 'Enable continue on failure' }).click()
    await expect(fallbackToggle).toBeEnabled()

    // Verify the fallback decision dropdown has both options
    await fallbackToggle.click()
    await expect(app.getByRole('option', { name: 'Approve' })).toBeVisible()
    await expect(app.getByRole('option', { name: 'Reject (default)' })).toBeVisible()
    // Close the dropdown
    await fallbackToggle.click()

    // Verify decision window label is present (use exact match to avoid strict mode violation)
    await expect(app.getByText('Decision window', { exact: true })).toBeVisible()

    // Close without saving
    const cancelButton = app.getByRole('button', { name: 'Cancel' })
    await cancelButton.click()
  })
})
