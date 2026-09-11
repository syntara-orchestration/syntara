import { test, expect, toAppUrl } from './fixtures'
import { createTestCredential, deleteCredentialByName, goToCredentialsList } from './helpers/credentials'
import { buildUniqueName, createBasicWorkflowViaApi } from './helpers/workflows'
import { apiRequest } from './utils/api'

test.describe('Navigational link affordance @pr-check', () => {
  test.describe('Credentials table', () => {
    test('credential name is a navigational link', async ({ app }) => {
      const { name } = await createTestCredential(app, { prefix: 'e2e-link' })
      try {
        await goToCredentialsList(app)

        // The credential name must render as an anchor link (SynLink renders <a> via TanStack Router),
        // not as plain text — verifies proper anchor semantics and PatternFly underline affordance.
        // Scoped to [data-label="Name"] to avoid matching the kebab "Actions for <name>" toggle.
        const credLink = app.locator('[data-label="Name"]').getByRole('link', { name })
        await expect(credLink).toBeVisible()

        // Clicking it must navigate to the credential detail page.
        await credLink.click()
        await expect(app).toHaveURL(/\/configuration\/credentials\//)
        await expect(app.locator('h1').filter({ hasText: name })).toBeVisible()
      } finally {
        await deleteCredentialByName(app, name)
      }
    })
  })

  test.describe('Workflows table', () => {
    test('workflow name is a navigational link', async ({ app }) => {
      const workflowName = buildUniqueName('e2e-navlink')
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'nav link test step')

      try {
        await app.goto(toAppUrl('/workflows'))
        await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

        // Konflux seed volume paginates the list; filter so the row is on page one.
        await app.getByPlaceholder('Filter by name').fill(workflowName)
        await app.getByRole('button', { name: 'Apply filter' }).click()

        const workflowLink = app.locator('[data-label="Name"]').getByRole('link', { name: workflowName })
        await expect(workflowLink).toBeVisible({ timeout: 15_000 })

        // Clicking it must navigate to the workflow builder.
        await workflowLink.click()
        await expect(app).toHaveURL(/\/workflow-builder\//)
      } finally {
        await apiRequest(app, 'delete', `/workflows/${id}`).catch(() => {})
      }
    })
  })

  test.describe('Workflow Runs table', () => {
    test('run ID is a navigational link', async ({ app }) => {
      const workflowName = buildUniqueName('e2e-runlink')
      const { id: workflowId } = await createBasicWorkflowViaApi(app, workflowName, 'run link test step')

      try {
        const runResp = await apiRequest(app, 'post', '/executions', {
          data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
        })
        const body = (await runResp.json()) as { id?: string }
        expect(body.id, 'POST /executions did not return an execution ID').toBeTruthy()
        if (!body.id) {
          throw new Error('POST /executions did not return an execution ID')
        }
        const executionId = body.id

        await app.goto(toAppUrl('/executions'))
        await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

        const grid = app.getByRole('grid')
        await expect(grid).toBeVisible({ timeout: 10_000 })

        const runLink = grid.locator('[data-label="Run ID"]').getByRole('link', { name: executionId })
        await expect(runLink).toBeVisible({ timeout: 10_000 })

        await runLink.click()
        await expect(app).toHaveURL(new RegExp(`/executions/${executionId}`))
      } finally {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    })
  })
})
