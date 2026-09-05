import { test, expect, toAppUrl } from './fixtures'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  createWorkflowWithTrigger,
  deleteWorkflow,
  publishWorkflowViaApi,
} from './helpers/workflows'

// Regression: React Compiler memoized the <Controller> element for the description
// field, causing React to bail out of re-renders and resetting the textarea value to
// "" after every keystroke. Only manifests in production builds (not dev mode).
test.describe('Publish dialog regression', () => {
  test('description textarea accepts multi-character input', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-publish-desc-input')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Desc input step')
      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByRole('button', { name: /Publish/i }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const descInput = dialog.getByLabel('Description')
      await descInput.pressSequentially('hello world')

      await expect(descInput).toHaveValue('hello world')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Workflow publish/unpublish', () => {
  test('new workflow shows Draft badge after save', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-publish-draft')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Draft step')
      await openWorkflowInBuilder(app, workflowName, id)

      await expect(app.getByText('Draft', { exact: true })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('publish button opens dialog with expected fields', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-publish-dialog')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Publish step')
      await openWorkflowInBuilder(app, workflowName, id)

      // Click Publish button in toolbar
      await app.getByRole('button', { name: /Publish/i }).click()

      // Verify dialog opens with expected content
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Publish workflow?')).toBeVisible()
      await expect(dialog.getByLabel('Version name')).toBeVisible()
      await expect(dialog.getByLabel('Description')).toBeVisible()

      // Version name should be pre-filled with a date
      const versionInput = dialog.getByLabel('Version name')
      await expect(versionInput).not.toHaveValue('')

      // Cancel without publishing
      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()

      // Badge should still be Draft (no publish happened)
      await expect(app.getByText('Draft', { exact: true })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('publish dialog submits without error', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-publish-submit')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Publish step')
      await openWorkflowInBuilder(app, workflowName, id)

      // Click Publish button in toolbar
      await app.getByRole('button', { name: /Publish/i }).click()

      // Submit the dialog
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: 'Publish workflow' }).click()

      // Dialog should close after submit
      await expect(dialog).not.toBeVisible({ timeout: 10_000 })

      // Badge should update to Published, proving the publish took effect
      await expect(app.getByText('Published', { exact: true })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('unpublish action returns workflow to Draft', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-unpublish-roundtrip')

    try {
      const { id, versionNumber } = await createBasicWorkflowViaApi(app, workflowName, 'Unpublish step')
      await publishWorkflowViaApi(app, id, versionNumber)
      await openWorkflowInBuilder(app, workflowName, id)

      // Confirm publish is reflected in builder
      await expect(app.getByText('Published', { exact: true })).toBeVisible()

      // Open kebab — Unpublish action should be available for a published workflow
      await app.getByRole('button', { name: 'Workflow actions' }).click()
      const unpublishItem = app.getByRole('menuitem', { name: /Unpublish workflow/i })
      await expect(unpublishItem).toBeVisible()
      await unpublishItem.click()

      // Badge should return to Draft
      await expect(app.getByText('Draft', { exact: true })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('status badge shows in workflow list', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-list-badge')

    try {
      const { id, versionNumber } = await createBasicWorkflowViaApi(app, workflowName, 'List badge step')

      // Navigate to workflow list
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Verify Draft badge appears in the Status column
      const row = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(row).toBeVisible()
      await expect(row.getByText('Draft', { exact: true })).toBeVisible()

      // Publish via API and verify the list reflects Published status
      await publishWorkflowViaApi(app, id, versionNumber)

      // Navigate away and back to force a fresh data fetch — re-applying the same
      // filter in place is a no-op and returns stale cached data.
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const updatedRow = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(updatedRow).toBeVisible()
      await expect(updatedRow.getByText('Published', { exact: true })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('publish button is disabled for workflow with no steps', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-empty-publish')

    try {
      await createWorkflowWithTrigger(app, workflowName)

      const publishBtn = app.getByRole('button', { name: /Publish workflow/i })
      await expect(publishBtn).toBeVisible()
      await expect(publishBtn).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
