/**
 * E2E Tests: Version History Panel (UI-7 through UI-12)
 *
 * Covers:
 * - UI-7: Version history panel display, filtering, date grouping
 * - UI-8: View-only mode when clicking a previous version
 * - UI-9: Restore version creates new draft
 * - UI-10: Back to editor returns to latest version
 * - UI-11: Publish specific version from history kebab
 * - UI-12: Export and open in new window from version history kebab
 */

import { type Page, test, expect, toAppUrl } from '../fixtures'
import { createWorkflowViaApi, updateWorkflowViaApi, deleteWorkflowViaApi } from '../helpers/workflow-versions'
import { buildUniqueName } from '../helpers/workflows'

async function openVersionHistory(app: Page) {
  await app.getByRole('button', { name: 'Workflow actions' }).click()
  await app.getByRole('menuitem', { name: 'Version history' }).click()
  await expect(app.getByRole('heading', { name: /Version history/i, level: 2 })).toBeVisible({ timeout: 10_000 })
}

async function clickVersionRow(app: Page, versionNumber: number) {
  await app
    .getByRole('listitem')
    .filter({ has: app.getByRole('button', { name: `Actions for version ${versionNumber}`, exact: true }) })
    .click()
}

test.describe('Version History Panel @pr-check', () => {
  test('UI-7: panel opens and shows versions with date grouping', async ({ app }) => {
    const name = buildUniqueName('e2e-vh-display')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await updateWorkflowViaApi(app, workflow.id, 'version 2')

      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('heading', { name: /Version history/i, level: 2 })).toBeVisible()
      await expect(app.getByText('Browse past saves and publishes.')).toBeVisible()
      await expect(app.getByRole('button', { name: /Filter by state/i })).toBeVisible()

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Actions for version 2', exact: true })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-8: clicking previous version enters view-only mode', async ({ app }) => {
    const name = buildUniqueName('e2e-vh-viewonly')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await updateWorkflowViaApi(app, workflow.id, 'version 2')

      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await clickVersionRow(app, 1)

      await expect(app.getByText(/Viewing/i)).toBeVisible({ timeout: 10_000 })
      await expect(app.getByRole('button', { name: /Restore version/i })).toBeVisible()
      await expect(app.getByRole('button', { name: /Back to editor/i })).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-9: restore version creates new draft', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-vh-restore')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await updateWorkflowViaApi(app, workflow.id, 'version 2')

      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await clickVersionRow(app, 1)

      await expect(app.getByText(/Viewing/i)).toBeVisible({ timeout: 10_000 })

      await app.getByRole('button', { name: /Restore version/i }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: /Restore/i }).click()

      await expect(app.getByText(/Viewing/i)).not.toBeVisible({ timeout: 10_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-10: back to editor returns to latest version', async ({ app }) => {
    const name = buildUniqueName('e2e-vh-back')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await updateWorkflowViaApi(app, workflow.id, 'version 2')

      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await clickVersionRow(app, 1)
      await expect(app.getByText(/Viewing/i)).toBeVisible({ timeout: 10_000 })

      await app.getByRole('button', { name: /Back to editor/i }).click()

      await expect(app.getByText(/Viewing/i)).not.toBeVisible({ timeout: 10_000 })
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-11: publish specific version from history kebab', async ({ app }) => {
    test.setTimeout(120_000)
    const name = buildUniqueName('e2e-vh-publish')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await updateWorkflowViaApi(app, workflow.id, 'version 2')

      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await app.getByRole('button', { name: 'Actions for version 1', exact: true }).click()
      await app.getByRole('menuitem', { name: /Publish this version/i }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /^Publish$/i }).click()

      await expect(app.getByRole('dialog')).not.toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-12: export from version history kebab downloads JSON', async ({ app }) => {
    const name = buildUniqueName('e2e-vh-export')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await app.getByRole('button', { name: 'Actions for version 1', exact: true }).click()

      const [download] = await Promise.all([
        app.waitForEvent('download'),
        app.getByRole('menuitem', { name: /Export workflow/i }).click(),
      ])

      expect(download.suggestedFilename()).toMatch(/\.json$/)
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })

  test('UI-12: open version in new window from history kebab', async ({ app }) => {
    const name = buildUniqueName('e2e-vh-newwindow')
    const workflow = await createWorkflowViaApi(app, name)

    try {
      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15_000 })

      await openVersionHistory(app)

      await expect(app.getByRole('button', { name: 'Actions for version 1', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await app.getByRole('button', { name: 'Actions for version 1', exact: true }).click()

      const [newPage] = await Promise.all([
        app.context().waitForEvent('page'),
        app.getByRole('menuitem', { name: /Open version in new window/i }).click(),
      ])

      await newPage.waitForLoadState()
      await expect(newPage).toHaveURL(/\/workflow-builder\//)
      await newPage.close()
    } finally {
      await deleteWorkflowViaApi(app, workflow.id)
    }
  })
})
