import { type Locator } from '@playwright/test'

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow } from './helpers/workflows'
import { createUserViaApi, deleteUserViaApi, type SeededUser } from './seeds/iam'
import { createIntegrationViaApi, deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { createRoleAssignmentViaApi, deleteRoleAssignmentViaApi, getAuthToken } from './utils/api'

async function assertWorkflowDeleteModal(modal: Locator, workflowName: string) {
  await expect(modal).toBeVisible()
  await expect(modal.getByText('Delete workflow?')).toBeVisible()
  await expect(modal.getByText(new RegExp(workflowName))).toBeVisible()
  await expect(
    modal
      .locator('p')
      .getByText(/will be deleted and any in-progress runs will stop immediately\. This action cannot be undone/)
  ).toBeVisible()
  await expect(modal.getByText(/dependent workflows|use this one as a step/)).toHaveCount(0)

  const checkbox = modal.getByRole('checkbox', {
    name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
  })
  await expect(checkbox).toBeVisible()
  await expect(checkbox).not.toBeChecked()

  const deleteButton = modal.getByRole('button', { name: 'Delete' })
  await expect(deleteButton).toBeDisabled()

  await checkbox.click()
  await expect(deleteButton).toBeEnabled()
}

test.describe('destructive modal UX compliance (AAP-72897)', () => {
  let seededUser: SeededUser | null = null
  let seededAssignment: { id: string } | null = null

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      const token = await getAuthToken(page)
      if (!token) throw new Error('destructive-modals beforeAll: could not obtain auth token')

      const prefix = buildUniqueName('e2e-dm')
      seededUser = await createUserViaApi(page, { username: `${prefix}-user`, token })

      seededAssignment = await createRoleAssignmentViaApi(page, {
        principal_id: seededUser.id,
        role_name: 'admin',
      })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    if (seededAssignment) {
      await deleteRoleAssignmentViaApi(page, seededAssignment.id)
    }
    if (seededUser) {
      await deleteUserViaApi(page, seededUser.id)
    }
    await page.close()
  })

  test('delete integration modal matches UX spec', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-delete-modal')
    let seededIntegration: SeededIntegration | null = null

    try {
      // Create integration via API
      const token = await getAuthToken(app)
      seededIntegration = await createIntegrationViaApi(app, { name: integrationName, token: token ?? undefined })
      expect(seededIntegration, 'Failed to create integration via API').toBeTruthy()

      await app.goto(toAppUrl('/configuration/integrations'))
      await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

      // Filter to find it
      await app.getByPlaceholder('Filter by name').fill(integrationName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const row = app.getByRole('row', { name: new RegExp(integrationName) })
      await expect(row).toBeVisible({ timeout: 30000 })

      // Open the kebab menu and click Delete integration
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: /Delete integration/i }).click()

      // Verify the modal matches the UX spec
      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()

      // Title should be "Delete integration?" with question mark
      await expect(modal.getByText('Delete integration?')).toBeVisible()

      // Body should use the spec format with bold resource name
      await expect(modal.getByText(new RegExp(integrationName))).toBeVisible()
      await expect(modal.getByText(/cannot be undone/)).toBeVisible()

      // Delete button should be disabled before checkbox is checked
      const deleteButton = modal.getByRole('button', { name: 'Delete' })
      await expect(deleteButton).toBeDisabled()

      // Checkbox should be present with the acknowledgement text
      const checkbox = modal.getByRole('checkbox')
      await expect(checkbox).toBeVisible()
      await expect(checkbox).not.toBeChecked()
      await expect(modal.getByText(/I understand this integration.*will be permanently deleted/)).toBeVisible()

      // After checking the checkbox, delete button should be enabled
      await checkbox.click()
      await expect(checkbox).toBeChecked()
      await expect(deleteButton).toBeEnabled()

      // Unchecking should disable the button again
      await checkbox.click()
      await expect(deleteButton).toBeDisabled()

      // Cancel button should use link variant and close the modal
      const cancelButton = modal.getByRole('button', { name: 'Cancel' })
      await expect(cancelButton).toBeVisible()
      await cancelButton.click()
      await expect(modal).not.toBeVisible()
    } finally {
      if (seededIntegration) {
        await deleteIntegrationViaApi(app, seededIntegration.id)
      }
    }
  })

  test('delete workflow modal has Tier 1 pattern: warning icon, acknowledgement checkbox', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-modal-wf')

    await createBasicWorkflowViaApi(app, workflowName, 'Modal test action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(row).toBeVisible({ timeout: 15000 })

      // Open kebab menu and click Delete
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: 'Delete workflow' }).click()

      const modal = app.getByRole('dialog')
      await assertWorkflowDeleteModal(modal, workflowName)

      // Cancel to keep the workflow for cleanup
      await modal.getByRole('button', { name: 'Cancel' }).click()
      await expect(modal).not.toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('builder delete workflow modal matches list copy', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-builder-delete-modal')
    const workflow = await createBasicWorkflowViaApi(app, workflowName, 'Modal test action')

    try {
      await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
      await expect(app.getByPlaceholder('Workflow name')).toBeVisible({ timeout: 15000 })

      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: 'Delete workflow' }).click()

      const modal = app.getByRole('dialog')
      await assertWorkflowDeleteModal(modal, workflowName)

      await modal.getByRole('button', { name: 'Cancel' }).click()
      await expect(modal).not.toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('unassign role modal has Tier 2 pattern: warning icon, no checkbox', async ({ app }) => {
    expect(seededUser, 'Seeded user not created in beforeAll').toBeTruthy()
    expect(seededAssignment, 'Seeded role assignment not created in beforeAll').toBeTruthy()
    if (!seededUser) {
      throw new Error('Seeded user not created in beforeAll')
    }

    // Navigate directly to the seeded user's detail page (they have a role assignment)
    await app.goto(toAppUrl(`/system-administration/access-management/users/${seededUser.id}`))
    await expect(app.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 10_000 })

    // Go to the Assignments tab
    const roleAssignmentsTab = app.getByRole('tab', { name: /Assignments/i })
    await expect(roleAssignmentsTab).toBeVisible({ timeout: 10_000 })
    await roleAssignmentsTab.click()

    // Open the kebab menu in the assignments table row and click Unassign
    const assignmentsTable = app.getByRole('grid')
    const kebabButton = assignmentsTable.getByRole('button', { name: /Actions|Kebab toggle/i })
    await expect(kebabButton).toBeVisible({ timeout: 10_000 })
    await kebabButton.click()
    await app.getByRole('menuitem', { name: /Unassign/i }).click()

    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()

    // Title ends with question mark
    await expect(modal.getByText('Unassign role?')).toBeVisible()

    // Tier 2: NO checkbox (reversible action)
    await expect(modal.getByRole('checkbox')).toHaveCount(0)

    // Confirm button should be enabled immediately (no checkbox gate)
    const confirmButton = modal.getByRole('button', { name: 'Unassign' })
    await expect(confirmButton).toBeEnabled()

    // Cancel to avoid side effects
    await modal.getByRole('button', { name: 'Cancel' }).click()
    await expect(modal).not.toBeVisible()
  })
})
