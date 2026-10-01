/**
 * E2E Tests: Workflow Builder Validation (UI-31)
 *
 * Covers: verification error banner when a workflow contains a disconnected node.
 */
import { test, expect } from '../fixtures'
import { buildUniqueName, createWorkflowWithTrigger, addScriptStepUnconnected } from '../helpers/workflows'
import { apiRequest } from '../utils/api'

test.describe('UI-31: Workflow Verification — Pre-Execution Validation', () => {
  test('verification error shown for a disconnected node', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-validation')

    // Create a workflow with just a trigger (saves successfully, gives us a workflow ID)
    await createWorkflowWithTrigger(app, workflowName)
    const workflowId = app.url().match(/workflow-builder\/([a-f0-9-]{36})/)?.[1]

    try {
      // Add a script node that is NOT connected to anything (dangling/orphaned)
      await addScriptStepUnconnected(app, 'Orphaned Step', 'echo "orphan"')

      // Trigger verification via the kebab menu (Save does not run validation — verification is a separate action)
      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: 'Verify workflow' }).click()

      // Validation error banner should appear (alert body is collapsed by default — expand it)
      await expect(app.getByRole('heading', { name: /Verification failed/i })).toBeVisible({ timeout: 10_000 })
      await app.getByRole('button', { name: /Danger alert details/i }).click()
      await expect(app.getByText(/not connected to the workflow/i)).toBeVisible()
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})
