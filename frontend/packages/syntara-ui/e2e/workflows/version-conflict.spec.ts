/**
 * E2E Tests: Concurrent Edit Conflict Detection (UI-13 through UI-17)
 *
 * Covers:
 * - UI-13: Conflict dialog appears on stale save
 * - UI-14: "Save as newest version" resolves conflict
 * - UI-15: "Create duplicate workflow" resolves conflict
 * - UI-16: "Refresh to latest" resolves conflict
 * - UI-17: Conflict dialog on publish and run attempts
 *
 * These tests simulate concurrent edits by using the API to save a new
 * version while the builder is open, then attempting to save/publish/run
 * from the UI.
 */

import { type Page, test, expect, toAppUrl } from '../fixtures'
import { createWorkflowViaApi, deleteWorkflowViaApi, simulateConcurrentSave } from '../helpers/workflow-versions'
import { buildUniqueName, deleteWorkflow, addScriptNode } from '../helpers/workflows'

async function openBuilderAndMakeChange(app: Page, workflowId: string) {
  await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
  await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

  await addScriptNode(app, 'Local Change', 'print("local")')
}

test.describe('Concurrent Edit Conflict Detection @pr-check', () => {
  test('UI-13: conflict dialog appears on stale save', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-dialog')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      await app.getByRole('button', { name: 'Save' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: 15_000 })
      await expect(dialog.getByText('Save conflict: newer version available')).toBeVisible()

      // Verify the conflict info paragraph renders version labels from the API
      // (should show dates or names, not bare numbers like "Version 2")
      const conflictInfo = dialog.getByText(/was saved by/)
      await expect(conflictInfo).toBeVisible()
      await expect(conflictInfo).not.toHaveText(/Version \d+ was saved by/)

      await expect(dialog.getByRole('button', { name: 'Save as newest version' })).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create duplicate workflow/i })).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Refresh to latest' })).toBeVisible()

      await dialog.getByRole('button', { name: 'Refresh to latest' }).click()
      await expect(dialog).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-14: save as newest version resolves conflict', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-save')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      await app.getByRole('button', { name: 'Save' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: 15_000 })

      await dialog.getByRole('button', { name: 'Save as newest version' }).click()

      await expect(dialog).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-15: create duplicate resolves conflict', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-dup')
    const workflow = await createWorkflowViaApi(app, name)
    let duplicateName: string | undefined

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      await app.getByRole('button', { name: 'Save' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: 15_000 })

      await dialog.getByRole('button', { name: /Create duplicate workflow/i }).click()

      await expect(app).toHaveURL(/\/workflow-builder\//, { timeout: 15_000 })

      const nameInput = app.getByPlaceholder('Workflow name')
      await expect(nameInput).toBeVisible({ timeout: 15_000 })
      duplicateName = await nameInput.inputValue()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
      if (duplicateName) {
        await deleteWorkflow(app, duplicateName)
      }
    }
  })

  test('UI-16: refresh to latest resolves conflict', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-refresh')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      await app.getByRole('button', { name: 'Save' }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: 15_000 })

      await dialog.getByRole('button', { name: 'Refresh to latest' }).click()

      await expect(dialog).not.toBeVisible({ timeout: 15_000 })
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-17: conflict dialog appears on publish attempt', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-publish')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      await app.getByRole('button', { name: /Publish workflow/i }).click()

      const publishDialog = app.getByRole('dialog')
      await expect(publishDialog).toBeVisible({ timeout: 15_000 })
      await publishDialog.getByRole('button', { name: /^Publish$/i }).click()

      await expect(app.getByText(/conflict: newer version available/i)).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Refresh to latest' }).click()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-17: conflict dialog appears on run attempt', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-conflict-run')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await openBuilderAndMakeChange(app, workflow.id)

      await simulateConcurrentSave(app, workflow.id)

      // Click Run — opens save-and-run confirmation dialog
      await app.getByRole('button', { name: 'Run' }).click()
      const runDialog = app.getByRole('dialog')
      await expect(runDialog).toBeVisible({ timeout: 15_000 })

      // Confirm the run — triggers save-before-run which detects the conflict
      await runDialog.getByRole('button', { name: /Save and run/i }).click()

      // The conflict dialog appears after the save detects the stale version
      await expect(app.getByText(/conflict: newer version available/i)).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Refresh to latest' }).click()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })
})
