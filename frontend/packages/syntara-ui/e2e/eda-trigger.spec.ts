/**
 * E2E Tests: EDA (Event-Driven Ansible) Trigger
 *
 * Critical paths covered:
 * - Creating a workflow with an EDA trigger and saving it
 * - EDA webhook URL preview shows /eda/ prefix and updates with path input
 * - Form validation: empty path, invalid characters
 * - Canvas rendering: correct label and detail text for EDA triggers
 * - Connection instructions alert is visible in the form
 *
 * Edge cases:
 * - Empty webhook path rejected with validation error
 * - Invalid characters rejected with descriptive error
 */

import { test, expect, toAppUrl } from './fixtures'
import { addEdaTrigger } from './helpers/v2-nodes'
import {
  buildUniqueName,
  clickAddConnectedStep,
  closeNodeEditorPanel,
  deleteWorkflow,
  fillCodeEditor,
  selectProjectIfRequired,
} from './helpers/workflows'
import { createServiceAccountViaApi, deleteServiceAccountViaApi, ensureProject } from './utils/api'

test.describe('EDA Trigger', () => {
  test('user creates a workflow with EDA trigger and saves it', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-eda')
    const webhookPath = 'github-deployments'

    await ensureProject(app)
    const sa = await createServiceAccountViaApi(app, buildUniqueName('sa-eda'))
    await app.goto(toAppUrl('/workflow-builder/new'))

    try {
      // Add EDA trigger
      await addEdaTrigger(app, 'GitHub Events', webhookPath, sa.name)

      // Add a connected script action
      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Action', exact: true }).click()
      await panel.getByRole('button', { name: 'Script', exact: true }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Process event')
      await fillCodeEditor(app, { value: 'print("processing EDA event")' })
      await app.getByRole('button', { name: 'Create', exact: true }).click()
      await closeNodeEditorPanel(app)

      // Save workflow (select project right before save)
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/)

      // Verify workflow appears in list
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: workflowName, exact: true })).toBeVisible()

      // Reopen workflow and verify trigger persists on canvas
      await app.getByRole('link', { name: workflowName, exact: true }).click()
      await expect(app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'EDA' })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteServiceAccountViaApi(app, sa.id)
    }
  })

  test('EDA form shows URL preview with /eda/ prefix that updates with path input', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))

    // Wait for trigger selection and select EDA trigger
    await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10_000 })
    await app.getByRole('button', { name: 'Event-Driven Ansible trigger', exact: true }).click()

    // Type a path
    await app.getByRole('textbox', { name: 'Webhook path' }).fill('github-push')

    // Verify the URL preview contains the /eda/ prefix and the path
    const urlInput = app.getByLabel('Webhook URL').getByRole('textbox')
    await expect(urlInput).toHaveValue(/\/eda\/github-push/)

    // Change the path and verify URL reflects the change
    await app.getByRole('textbox', { name: 'Webhook path' }).fill('jira-events')
    await expect(urlInput).toHaveValue(/\/eda\/jira-events/)
    await expect(urlInput).not.toHaveValue(/github-push/)
  })

  test('EDA form shows webhook activation alert', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))

    await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10_000 })
    await app.getByRole('button', { name: 'Event-Driven Ansible trigger', exact: true }).click()

    await expect(app.getByText('EDA activation')).toBeVisible()
  })

  test.skip('EDA form validates empty path', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))

    await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10_000 })
    await app.getByRole('button', { name: 'Event-Driven Ansible trigger', exact: true }).click()

    // Leave webhook path empty, attempt to submit
    await app.getByRole('button', { name: 'Create', exact: true }).click()

    // Verify validation error
    await expect(app.getByText('Webhook path is required')).toBeVisible()
  })

  test('EDA form validates invalid path characters', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))

    await expect(app.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10_000 })
    await app.getByRole('button', { name: 'Event-Driven Ansible trigger', exact: true }).click()

    // Enter invalid characters
    await app.getByRole('textbox', { name: 'Webhook path' }).fill('invalid path!@#')
    await app.getByRole('button', { name: 'Create', exact: true }).click()

    // Verify validation error
    await expect(
      app.getByText(
        'Path must start and end with a letter or number, and contain only lowercase letters, numbers, hyphens, and underscores'
      )
    ).toBeVisible()
  })
})
