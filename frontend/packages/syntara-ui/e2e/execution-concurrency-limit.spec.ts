/**
 * E2E: When the API returns 429 (concurrency limit reached), the builder
 * shows an error alert with the detail message from the RFC 9457 response body.
 *
 * The concurrency limit is enforced server-side. These tests use page.route()
 * to inject a 429 response without needing to spin up N real workflows.
 */

import { test, expect } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow, openWorkflowInBuilder } from './helpers/workflows'
import { ensureProject } from './utils/api'

const CONCURRENCY_LIMIT_BODY = {
  type: 'https://api.example.com/errors/rate-limited',
  title: 'Workflow Concurrency Limit Reached',
  detail:
    'Workflow concurrency limit reached: 10/10 active workflows. Wait for a workflow to complete before starting a new one.',
  code: 'WORKFLOW_CONCURRENCY_LIMIT',
  retryable: true,
  status: 429,
}

test.describe('Execution Concurrency Limit', () => {
  test('shows error alert with detail message when API returns 429 on workflow start', async ({ app }) => {
    await ensureProject(app)
    const workflowName = buildUniqueName('e2e-concurrency')
    const { id } = await createBasicWorkflowViaApi(app, workflowName)
    await openWorkflowInBuilder(app, workflowName, id)

    try {
      // Register route BEFORE clicking Run so the handler is in place when the request fires
      await app.route('**/api/v1/executions', (route) => {
        if (route.request().method() === 'POST') {
          return route.fulfill({
            status: 429,
            contentType: 'application/problem+json',
            body: JSON.stringify(CONCURRENCY_LIMIT_BODY),
          })
        }
        return route.continue()
      })

      const responsePromise = app.waitForResponse(
        (resp) => resp.url().includes('/api/v1/executions') && resp.request().method() === 'POST'
      )
      await app.getByRole('button', { name: /^Run$/ }).click()
      await app.getByRole('button', { name: 'Run now' }).click()
      await responsePromise

      // PF6 toast AlertGroup uses role="list"; individual items have class pf-v6-c-alert
      const alert = app.locator('.pf-v6-c-alert-group .pf-v6-c-alert')
      await expect(alert.filter({ hasText: /concurrency limit/i })).toBeVisible()
      await expect(alert.filter({ hasText: /10\/10 active workflows/i })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
