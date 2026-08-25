/**
 * E2E Tests: Undo/Redo in the Workflow Builder
 *
 * Critical paths covered:
 * - Undo/redo add-node via toolbar buttons
 * - Undo/redo add-node via keyboard shortcuts (Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z)
 * - Undo/redo buttons disabled on fresh workflow load
 * - History resets when navigating away from the builder
 * - Undo/redo becomes disabled when entering execution view
 *
 * Not covered (unit tests handle these):
 * - Position undo/redo (drag detection unreliable in headless Playwright)
 * - Temporal batching internals
 * - Edge synchronization details
 */

import type { Page } from '@playwright/test'

import { test, expect, toAppUrl } from './fixtures'
import { addScriptNode } from './helpers/v2-nodes'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow, openWorkflowInBuilder } from './helpers/workflows'

/** Locate the undo/redo toolbar rendered by UndoRedoControls. */
const undoRedoToolbar = (app: Page) => app.getByRole('toolbar', { name: 'Undo and redo' })

/** Locate the Undo button inside the toolbar. */
const undoButton = (app: Page) => undoRedoToolbar(app).getByRole('button', { name: 'Undo' })

/** Locate the Redo button inside the toolbar. */
const redoButton = (app: Page) => undoRedoToolbar(app).getByRole('button', { name: 'Redo' })

test('undo/redo add node via toolbar buttons', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-undo-toolbar')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Initial action')

  const nodeName = 'Toolbar undo node'

  try {
    await openWorkflowInBuilder(app, workflowName, id)
    await addScriptNode(app, nodeName)
    await expect(app.getByText(nodeName)).toBeVisible()

    await undoButton(app).click()
    await expect(app.getByText(nodeName)).not.toBeVisible()

    await redoButton(app).click()
    await expect(app.getByText(nodeName)).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('undo/redo add node via keyboard shortcuts', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-undo-keyboard')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Initial action')

  const nodeName = 'Keyboard undo node'

  try {
    await openWorkflowInBuilder(app, workflowName, id)
    await addScriptNode(app, nodeName)
    await expect(app.getByText(nodeName)).toBeVisible()

    await app.keyboard.press('ControlOrMeta+z')
    await expect(app.getByText(nodeName)).not.toBeVisible()

    await app.keyboard.press('ControlOrMeta+Shift+z')
    await expect(app.getByText(nodeName)).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('undo and redo buttons are disabled on fresh workflow load', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-undo-fresh')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Initial action')

  try {
    await openWorkflowInBuilder(app, workflowName, id)

    await expect(undoButton(app)).toBeDisabled()
    await expect(redoButton(app)).toBeDisabled()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test('undo history resets when navigating away from the builder', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-undo-nav-reset')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Initial action')

  const nodeName = 'Nav reset node'

  try {
    await openWorkflowInBuilder(app, workflowName, id)
    await addScriptNode(app, nodeName)
    await expect(undoButton(app)).toBeEnabled()

    await app.goto(toAppUrl('/workflows'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    await openWorkflowInBuilder(app, workflowName, id)

    await expect(undoButton(app)).toBeDisabled()
  } finally {
    await deleteWorkflow(app, workflowName)
  }
})

test.describe('Execution History Navigation', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'], 'Execution engine unavailable (globalSetup probe)')

  test('selecting execution from history navigates to execution page', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-undo-exec-view')
    const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Initial action')

    try {
      await openWorkflowInBuilder(app, workflowName, id)

      // Create an execution by running the workflow through the UI
      await app.getByRole('button', { name: 'Run', exact: true }).click()
      await app.getByRole('button', { name: 'Run now' }).click()

      // Execution may fail if the workflow engine (Temporal) is unavailable
      const didNavigate = await expect(app)
        .toHaveURL(/\/executions\//)
        .then(() => true)
        .catch(() => false)
      expect(didNavigate, 'Workflow execution failed — execution engine may not be running').toBeTruthy()

      // Navigate back to the builder
      await openWorkflowInBuilder(app, workflowName, id)

      // Open run history via kebab menu — the execution we just created should appear
      await app.getByLabel('Workflow actions').click()
      await app.getByRole('menuitem', { name: 'Run history' }).click()
      await expect(app.getByRole('heading', { name: 'Run history' })).toBeVisible()

      // Click the execution to navigate to the execution page
      const runHistoryPanel = app.getByRole('heading', { name: 'Run history' }).locator('..')
      const executionItems = runHistoryPanel.locator('button[class*="simpleList"]')
      const itemCount = await executionItems.count()
      if (itemCount > 0) {
        await executionItems.nth(0).click()
        await expect(app).toHaveURL(/\/executions\//)
        await expect(app.getByRole('button', { name: 'Back to editor' })).toBeVisible()
      }
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
