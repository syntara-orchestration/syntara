import { type Locator } from '@playwright/test'

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow } from './helpers/workflows'
import {
  createRoleAssignmentViaApi,
  createUserViaApi,
  deleteRoleAssignmentViaApi,
  deleteUserViaApi,
  type SeededRoleAssignment,
  type SeededUser,
} from './seeds/iam'
import { createIntegrationViaApi, deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { ensureProject, getAuthToken } from './utils/api'

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
  let seededAssignment: SeededRoleAssignment | null = null

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    const token = await getAuthToken(page)
    if (token) {
      const prefix = buildUniqueName('e2e-dm')
      seededUser = await createUserViaApi(page, { username: `${prefix}-user`, token })

      if (seededUser) {
        const project = await ensureProject(page)
        if (project) {
          seededAssignment = await createRoleAssignmentViaApi(page, project.id, {
            userId: seededUser.id,
            roleName: 'admin',
            token,
          })
        }
      }
    }
    await page.close()
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    if (seededAssignment) {
      await deleteRoleAssignmentViaApi(page, seededAssignment.projectId, seededAssignment.id)
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
      expect(seededIntegration).not.toBeNull()

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
    await app.goto(toAppUrl('/system-administration/access-management/users'))

    const table = app.getByRole('grid', { name: 'Users table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No user data available; seed data required')

    // Navigate to first user's role assignments
    const firstRow = table.locator('tbody tr:first-child')
    const firstUserLink = firstRow.getByRole('link')
    await expect(firstUserLink).toBeVisible()
    await firstUserLink.click()

    // Go to the Assignments tab
    const roleAssignmentsTab = app.getByRole('tab', { name: /Assignments/i })
    const hasRoleTab = await roleAssignmentsTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasRoleTab, 'No role assignments tab available')

    await roleAssignmentsTab.click()

    // Find an unassign button in the assignments table
    const assignmentsTable = app.getByRole('grid')
    const unassignButton = assignmentsTable.getByRole('button', { name: /Unassign/i })
    const hasUnassign = await unassignButton
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasUnassign, 'No role assignments available to unassign')

    await unassignButton.click()

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
