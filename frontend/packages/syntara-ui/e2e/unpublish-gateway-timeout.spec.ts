/**
 * UI check for AAP-87692: unpublish from the builder must return Draft
 * even when Temporal schedule cleanup is slow. Against a healthy local
 * Temporal this asserts the happy path (200, success toast, Draft badge)
 * and that the unpublish request does not sit until a gateway timeout.
 */
import { test, expect } from './fixtures'
import { buildUniqueName, deleteWorkflow, openWorkflowInBuilder } from './helpers/workflows'
import { createWorkflowViaApi, publishWorkflowViaApi } from './utils/api'

test.describe('Builder unpublish (AAP-87692)', () => {
  test('scheduled workflow unpublish returns Draft without a failure toast', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-unpublish-scheduled')

    try {
      const { id, versionNumber } = await createWorkflowViaApi(
        app,
        workflowName,
        [
          {
            id: 'trigger_schedule',
            type: 'scheduled_trigger',
            name: 'Schedule',
            parameters: {
              schedule_type: 'interval',
              interval: 'R/2024-01-01T00:00:00Z/PT5M',
              missed_schedule_policy: 'skip',
            },
          },
        ],
        [
          {
            id: 'action_1',
            type: 'script',
            name: 'Script',
            parameters: { language: 'python', code: 'print("hello")' },
          },
        ],
        [{ from: 'trigger_schedule', to: 'action_1' }]
      )
      await publishWorkflowViaApi(app, id, versionNumber)
      await openWorkflowInBuilder(app, workflowName, id)
      await expect(app.getByText('Published', { exact: true })).toBeVisible()

      const unpublishWait = app.waitForResponse(
        (response) =>
          response.url().includes(`/api/v1/workflows/${id}/unpublish`) && response.request().method() === 'POST'
      )
      const started = Date.now()
      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: /Unpublish workflow/i }).click()
      const unpublishResp = await unpublishWait
      const elapsedMs = Date.now() - started

      expect(unpublishResp.status(), `unpublish HTTP ${unpublishResp.status()} in ${elapsedMs}ms`).toBe(200)
      expect(elapsedMs, `unpublish took ${elapsedMs}ms`).toBeLessThan(8_000)
      await expect(app.getByText('Failed to unpublish workflow')).toHaveCount(0)
      await expect(app.getByText('Workflow unpublished successfully')).toBeVisible({ timeout: 10_000 })
      await expect(app.getByText('Draft', { exact: true })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
