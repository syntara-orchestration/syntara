/**
 * E2E Tests: Copy Run to Editor
 *
 * Critical paths covered:
 * - "Copy to editor" button visible on execution detail page
 * - Confirmation dialog opens with correct content
 * - "Replace current workflow" navigates to builder with workflow loaded
 * - "Fork as new workflow" creates a new workflow and navigates to its builder
 * - Cancelling stays on execution page
 *
 * Edge cases:
 * - Dialog cancellation (stays on execution page)
 */

import { type Page, test, expect, toAppUrl } from './fixtures'
import { expectCanvasStepTitleVisible } from './helpers/canvas-interaction'
import { waitForExecutionTerminal } from './helpers/workflow-run'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  deleteWorkflow,
  openWorkflowInBuilder,
  waitForUIReady,
} from './helpers/workflows'
import { publishWorkflowViaApi, deleteWorkflowViaApi } from './utils/api'

/** Run a workflow from the Workflows list page and wait for navigation to the execution detail page. */
async function runWorkflowFromList(app: Page, workflowName: string) {
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const row = app.getByRole('row', { name: new RegExp(workflowName) })
  await expect(row).toBeVisible()

  // Wait for any loading states before interacting with the kebab
  await waitForUIReady(app)

  // Open kebab menu and click "Run published version"
  await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
  await app.getByRole('menuitem', { name: 'Run published version' }).click()

  // Confirm run in the dialog
  await app.getByRole('button', { name: 'Run now' }).click()

  // The Workflows page navigates to /executions/<id> on success
  await expect(app).toHaveURL(/\/executions\//, { timeout: 30_000 })
}

function executionIdFromPageUrl(page: Page): string {
  const executionId = page.url().match(/\/executions\/([^/?]+)/)?.[1]
  if (!executionId) {
    throw new Error('Expected execution detail URL with execution id')
  }
  return executionId
}

async function confirmCopyToEditorInBuilder(app: Page) {
  await app.getByRole('button', { name: 'Copy to editor' }).click()
  await expect(app.getByRole('heading', { name: 'Copy run to editor' })).toBeVisible()
  const replaceButton = app.getByRole('dialog').getByRole('button', { name: 'Replace current workflow' })
  await replaceButton.click()
  await expect(app).toHaveURL(/\/workflow-builder\//, { timeout: 30_000 })
  await waitForUIReady(app)
  await expect(app.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
  await expect(app.getByText('Run copied to editor')).toBeVisible({ timeout: 60_000 })
  await expect(async () => {
    await expect(app.getByRole('heading', { name: /run details/i })).toBeVisible()
  }).toPass({ timeout: 120_000, intervals: [2_000] })
}

test.describe('Copy Run to Editor', () => {
  test.skip(!process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'], 'Execution engine unavailable (globalSetup probe)')
  test('replaces current workflow via confirmation dialog', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-copy-to-editor')
    const { id, versionNumber } = await createBasicWorkflowViaApi(app, workflowName, 'Copy action')

    try {
      await publishWorkflowViaApi(app, id, versionNumber)

      // Run the workflow from the list page (navigates to /executions/<id>)
      await runWorkflowFromList(app, workflowName)

      // "Copy to editor" renders immediately on the execution detail page regardless of run status
      await expect(app.getByRole('button', { name: 'Copy to editor' })).toBeVisible({ timeout: 15_000 })

      // Click "Copy to editor"
      await app.getByRole('button', { name: 'Copy to editor' }).click()

      // Verify confirmation dialog appears
      await expect(app.getByRole('heading', { name: 'Copy run to editor' })).toBeVisible()
      await expect(app.getByText(/Copy this specific run of the automation/)).toBeVisible()

      // Click Replace
      const replaceButton = app.getByRole('dialog').getByRole('button', { name: 'Replace current workflow' })
      await replaceButton.click()

      // Verify navigation to builder with workflow loaded
      await expect(app).toHaveURL(/\/workflow-builder\//)
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 15_000 })
      await expect(app.getByRole('heading', { name: /run details/i })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('copy from run history keeps run details after workflow was already open in builder', async ({ app }) => {
    // Konflux: poll + history list + run-details retries can exceed the default slow ceiling (180s).
    test.setTimeout(360_000)

    const workflowName = buildUniqueName('e2e-copy-history')
    const { id, versionNumber } = await createBasicWorkflowViaApi(app, workflowName, 'History copy action')

    try {
      await publishWorkflowViaApi(app, id, versionNumber)
      await runWorkflowFromList(app, workflowName)
      const executionUrl = app.url()
      const executionId = executionIdFromPageUrl(app)
      await waitForExecutionTerminal(app, executionId, 120_000)

      await openWorkflowInBuilder(app, workflowName, id)
      await expectCanvasStepTitleVisible(app, 'Manual trigger', { timeout: 30_000 })
      await app.goto(executionUrl)
      await waitForUIReady(app)

      await expect(app.getByRole('button', { name: 'Copy to editor' })).toBeVisible({ timeout: 15_000 })
      await app.getByRole('button', { name: 'Run history' }).click()
      await expect(app.getByRole('heading', { name: 'Run history' })).toBeVisible()

      const runHistoryList = app.getByRole('list', { name: 'Run history list' })
      const executionRow = runHistoryList.getByRole('link', { name: /^Execution from / })
      await expect(async () => {
        await expect(executionRow).toBeVisible()
      }).toPass({ timeout: 60_000, intervals: [2_000] })
      await executionRow.click()
      await waitForUIReady(app)

      await expect(app.getByRole('button', { name: 'Copy to editor' })).toBeVisible({ timeout: 15_000 })
      await confirmCopyToEditorInBuilder(app)
      await expect(app.getByText('Run copied to editor')).toBeVisible({ timeout: 30_000 })
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 30_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('forks execution as new workflow', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-copy-fork')
    const { id: forkId, versionNumber: forkVersionNumber } = await createBasicWorkflowViaApi(
      app,
      workflowName,
      'Fork action'
    )
    let forkedWorkflowId: string | undefined

    try {
      await publishWorkflowViaApi(app, forkId, forkVersionNumber)

      // Run the workflow from the list page (navigates to /executions/<id>)
      await runWorkflowFromList(app, workflowName)

      // "Copy to editor" renders immediately on the execution detail page regardless of run status
      await expect(app.getByRole('button', { name: 'Copy to editor' })).toBeVisible({ timeout: 15_000 })

      // Click "Copy to editor"
      await app.getByRole('button', { name: 'Copy to editor' }).click()
      await expect(app.getByRole('heading', { name: 'Copy run to editor' })).toBeVisible()

      // Click Fork
      const forkButton = app.getByRole('dialog').getByRole('button', { name: 'Fork as new workflow' })
      await forkButton.click()

      // Verify navigation to builder with a new workflow
      await expect(app).toHaveURL(/\/workflow-builder\//, { timeout: 15_000 })

      // Capture the forked workflow ID from the URL immediately — before any assertions
      // that could fail — so cleanup always has the ID it needs.
      const urlMatch = app.url().match(/\/workflow-builder\/([^/?]+)/)
      forkedWorkflowId = urlMatch?.[1]

      // Verify the workflow name contains the copy pattern
      const nameInput = app.getByPlaceholder('Workflow name')
      await expect(nameInput).toBeVisible({ timeout: 15_000 })
      const forkedWorkflowName = await nameInput.inputValue()
      expect(forkedWorkflowName).toContain('- copy-')
    } finally {
      await deleteWorkflow(app, workflowName)
      if (forkedWorkflowId) {
        await deleteWorkflowViaApi(app, forkedWorkflowId)
      }
    }
  })

  test('cancelling the dialog stays on execution page', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-copy-cancel')
    const { id: cancelId, versionNumber: cancelVersionNumber } = await createBasicWorkflowViaApi(
      app,
      workflowName,
      'Cancel action'
    )

    try {
      await publishWorkflowViaApi(app, cancelId, cancelVersionNumber)

      // Run the workflow from the list page (navigates to /executions/<id>)
      await runWorkflowFromList(app, workflowName)

      // "Copy to editor" renders immediately on the execution detail page regardless of run status
      await expect(app.getByRole('button', { name: 'Copy to editor' })).toBeVisible({ timeout: 15_000 })

      // Open dialog and cancel
      await app.getByRole('button', { name: 'Copy to editor' }).click()
      await expect(app.getByRole('heading', { name: 'Copy run to editor' })).toBeVisible()
      await app.getByRole('button', { name: 'Cancel' }).click()

      // Verify dialog closed and still on execution page
      await expect(app.getByRole('heading', { name: 'Copy run to editor' })).not.toBeVisible()
      await expect(app).toHaveURL(/\/executions\//)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
