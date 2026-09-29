/**
 * E2E Tests: Run Button Visibility
 *
 * The Run button is always visible in the builder toolbar. It is disabled
 * until at least one trigger step is placed on the canvas AND the workflow
 * has been saved.
 *
 * Critical paths covered:
 * - Run button is visible but disabled on a new empty workflow (no triggers)
 * - Run button stays disabled after adding a trigger until the workflow is saved
 * - Run button is visible and enabled on a saved workflow with a trigger
 */

import { test, expect, toAppUrl } from './fixtures'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  deleteWorkflow,
  openWorkflowInBuilder,
  selectProjectIfRequired,
} from './helpers/workflows'
import { ensureProject } from './utils/api'

test.describe('Run Button Visibility', () => {
  test('Run button is visible but disabled on a new empty workflow', async ({ app }) => {
    await ensureProject(app)
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    await selectProjectIfRequired(app)

    const runButton = app.getByRole('button', { name: /^Run$/ })
    await expect(runButton).toBeVisible()
    await expect(runButton).toHaveAttribute('aria-disabled', 'true')
  })

  test('Run button stays disabled until workflow is saved', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-run-btn')
    await ensureProject(app)
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    try {
      await selectProjectIfRequired(app)

      const runButton = app.getByRole('button', { name: /^Run$/ })
      await expect(runButton).toBeVisible()
      await expect(runButton).toHaveAttribute('aria-disabled', 'true')

      // Add a manual trigger — Run should still be disabled (unsaved)
      await app.getByRole('button', { name: 'Manual trigger' }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
      await app.getByRole('button', { name: 'Create' }).click()
      await expect(runButton).toHaveAttribute('aria-disabled', 'true')

      // Save the workflow
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save workflow' }).click()
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

      // Run button should now be enabled (saved + has trigger)
      await expect(runButton).toBeVisible()
      await expect(runButton).not.toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('Run button is visible on a saved workflow with a trigger', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-run-saved')
    const { id } = await createBasicWorkflowViaApi(app, workflowName)
    await openWorkflowInBuilder(app, workflowName, id)

    try {
      const runButton = app.getByRole('button', { name: /^Run$/ })
      await expect(runButton).toBeVisible()
      await expect(runButton).not.toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
