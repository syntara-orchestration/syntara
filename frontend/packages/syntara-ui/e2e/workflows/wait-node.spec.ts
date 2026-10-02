/**
 * E2E Tests: Wait Node Configuration [UI-17]
 *
 * Critical paths covered:
 * - Adding a Wait node to the workflow canvas
 * - Configuring duration-based wait with time units (seconds, minutes, hours, days)
 * - Saving and verifying configuration persistence
 * - Reopening saved nodes to verify data persists
 *
 * Edge cases:
 * - Different time units (seconds, minutes, hours, days)
 * - Multiple time units combined (e.g., 1 hour 30 minutes)
 * - Reconfiguring duration values
 *
 * Note: Based on actual implementation (Screenshot 2026-06-26), only duration mode
 * is supported. Timestamp-based wait mentioned in test procedure is not implemented.
 */

import { test, expect } from '../fixtures'
import { addWaitStep } from '../helpers/v2-steps-loop'
import {
  buildUniqueName,
  closeStepEditorPanel,
  deleteWorkflow,
  openStepForEditing,
  saveWorkflow,
  startWorkflowWithTrigger,
  verifyStepVisible,
} from '../helpers/workflows'

test.describe('Wait Node Configuration', () => {
  test('adds Wait node with duration and verifies persistence', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-wait')

    try {
      await startWorkflowWithTrigger(app)

      // Add Wait node with 30 seconds
      await addWaitStep(app, 'Wait 30s', { seconds: 30 })
      await verifyStepVisible(app, 'Wait 30s')

      // Save and verify persistence
      // saveWorkflow now gates on the create response, so no URL guard is needed
      await saveWorkflow(app, workflowName)

      // Reopen to verify configuration persisted
      await openStepForEditing(app, 'Wait 30s')
      await expect(app.getByLabel('Seconds')).toHaveValue('30')
      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('configures Wait node with multiple time units', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-wait-multi')

    try {
      await startWorkflowWithTrigger(app)

      // Add Wait node with hours and minutes
      await addWaitStep(app, 'Wait 1h 30m', { hours: 1, minutes: 30 })
      await saveWorkflow(app, workflowName)

      // Verify both time units persisted
      await openStepForEditing(app, 'Wait 1h 30m')
      await expect(app.getByLabel('Hours')).toHaveValue('1')
      await expect(app.getByLabel('Minutes')).toHaveValue('30')
      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('configures Wait node with all time units combined', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-wait-all')

    try {
      await startWorkflowWithTrigger(app)

      // Add Wait node with all four time units
      await addWaitStep(app, 'Wait all units', {
        days: 1,
        hours: 2,
        minutes: 30,
        seconds: 45,
      })
      await saveWorkflow(app, workflowName)

      // Verify all time units persisted correctly
      await openStepForEditing(app, 'Wait all units')
      await expect(app.getByLabel('Days')).toHaveValue('1')
      await expect(app.getByLabel('Hours')).toHaveValue('2')
      await expect(app.getByLabel('Minutes')).toHaveValue('30')
      await expect(app.getByLabel('Seconds')).toHaveValue('45')
      await closeStepEditorPanel(app)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('edits Wait node duration via Update button', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-wait-edit')

    try {
      await startWorkflowWithTrigger(app)

      // Add Wait node with minimal duration
      await addWaitStep(app, 'Wait node', { seconds: 1 })

      // Edit the duration
      await openStepForEditing(app, 'Wait node')
      await app.getByLabel('Seconds').fill('30')
      await app.getByLabel('Minutes').fill('10')

      // Save with Update button
      const updateButton = app.getByRole('button', { name: 'Update' })
      await expect(updateButton).toBeEnabled()
      await updateButton.click()
      await expect(updateButton).not.toBeAttached({ timeout: 15_000 })
      await closeStepEditorPanel(app)

      // Verify the edit persisted
      await openStepForEditing(app, 'Wait node')
      await expect(app.getByLabel('Minutes')).toHaveValue('10')
      await expect(app.getByLabel('Seconds')).toHaveValue('30')
      await closeStepEditorPanel(app)

      await saveWorkflow(app, workflowName)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
