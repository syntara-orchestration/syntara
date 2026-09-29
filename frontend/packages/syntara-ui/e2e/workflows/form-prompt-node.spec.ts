import { test, expect, toAppUrl } from '../fixtures'
import { addFormPromptNodeWithBranches, addManualTrigger } from '../helpers/v2-nodes'
import { buildUniqueName, waitForUIReady } from '../helpers/workflows'
import { apiRequest } from '../utils/api'

test.describe('Form prompt workflow creation', () => {
  test('connects submitted and fallback branches, saves, and reloads', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-prompt-branches')
    let workflowId: string | undefined

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual Start')
      await addFormPromptNodeWithBranches(app, 'Intake Form')

      await expect(app.getByText('Intake Form submitted path')).toBeVisible({ timeout: 10_000 })

      const workflowNameInput = app.getByPlaceholder('Workflow name')
      await workflowNameInput.fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/\/workflow-builder\/[^/]+/, { timeout: 15_000 })
      workflowId = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]

      await app.reload()
      await waitForUIReady(app)
      await expect(app.getByText('Intake Form')).toBeVisible({ timeout: 15_000 })
      await expect(app.getByText('Intake Form submitted path')).toBeVisible({ timeout: 15_000 })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})
