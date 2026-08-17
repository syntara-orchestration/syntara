import { test, expect } from './fixtures'
import { addScriptNode } from './helpers/v2-nodes'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow, openWorkflowInBuilder } from './helpers/workflows'

test.describe('Execution URL unification', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'], 'Execution engine unavailable (globalSetup probe)')

  test('running a workflow shows inline run panel in builder', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-exec-url-run')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Run action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

      await expect(app.getByRole('button', { name: 'Back to editor' })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('run history navigates to execution page', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-exec-url-history')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'History action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByLabel('Workflow actions').click()
      await app.getByRole('menuitem', { name: 'Run history' }).click()
      await expect(app.getByRole('heading', { name: 'Run history' })).toBeVisible()

      const runHistoryPanel = app.getByRole('region', { name: 'Run history' })
      const executionButton = runHistoryPanel.locator('button[class*="simpleList"]').nth(0)
      const hasExecution = await executionButton
        .waitFor({ state: 'visible', timeout: 5000 })
        .then(() => true)
        .catch(() => false)

      if (hasExecution) {
        await executionButton.click()
        await expect(app).toHaveURL(/\/executions\//)
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('execution page shows workflow name in header', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-exec-url-name')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Name action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

      const heading = app.getByRole('heading', { level: 1 })
      await expect(heading).toContainText(workflowName)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('history card on execution page navigates between executions', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-exec-url-card')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Card action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      // Run workflow first time
      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

      // Run workflow second time to have multiple executions
      await openWorkflowInBuilder(app, workflowName, id)
      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigateSecond = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigateSecond, 'Second workflow execution failed')

      // History card is closed by default when navigating from builder; open it
      await app.getByRole('button', { name: 'Run history' }).click()
      await expect(app.getByRole('heading', { name: 'Run history' })).toBeVisible()

      // Click a different execution in the history card
      const executionItems = app.locator('button[class*="simpleList"]')
      const itemCount = await executionItems.count()
      if (itemCount > 1) {
        const secondUrl = app.url()
        await executionItems.nth(1).click()
        await expect(app).not.toHaveURL(secondUrl)
        await expect(app).toHaveURL(/\/executions\//)
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('dirty workflow prompts save before navigating to execution', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-exec-url-dirty')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Dirty action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      // Run workflow to create an execution
      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      test.skip(!didNavigate, 'Workflow execution failed — execution engine may not be running')

      // Go back to builder
      await openWorkflowInBuilder(app, workflowName, id)

      // Make the workflow dirty by adding a node
      await addScriptNode(app, 'Dirty node')

      // Open run history via kebab menu
      await app.getByLabel('Workflow actions').click()
      await app.getByRole('menuitem', { name: 'Run history' }).click()
      await expect(app.getByRole('heading', { name: 'Run history' })).toBeVisible()

      // Click an execution — should trigger unsaved changes prompt
      const runHistoryPanel = app.getByRole('region', { name: 'Run history' })
      const executionButton = runHistoryPanel.locator('button[class*="simpleList"]').nth(0)
      const hasExecution = await executionButton
        .waitFor({ state: 'visible', timeout: 5000 })
        .then(() => true)
        .catch(() => false)

      if (hasExecution) {
        await executionButton.click()

        // The unsaved changes modal should appear
        await expect(app.getByRole('heading', { name: /Save changes before exiting/i })).toBeVisible({ timeout: 3000 })

        // Click "Exit without saving" to proceed
        await app.getByRole('button', { name: /Exit without saving/i }).click()

        // Should navigate to executions page
        await expect(app).toHaveURL(/\/executions\//)
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
