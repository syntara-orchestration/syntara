/**
 * E2E Tests: Service Accounts — Role Assignments Tab
 *
 * Test cases covered:
 * - UI-10: Cross-project role assignment for service accounts
 */
import { test, expect } from './fixtures'
import { createTestServiceAccount, deleteServiceAccountViaApi, goToServiceAccountTab } from './helpers/service-accounts'

test.describe('UI-10: Cross-Project Role Assignment', () => {
  let sa: { id: string; name: string }

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sa = await createTestServiceAccount(page, { prefix: 'sa-cross-proj' })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    if (!sa) return
    const page = await browser.newPage()
    try {
      await deleteServiceAccountViaApi(page, sa.id)
    } finally {
      await page.close()
    }
  })

  test('assigns a project-scoped role from a different project', async ({ app }) => {
    await goToServiceAccountTab(app, sa, 'Assignments')

    // Click "Assign role" button
    await app.getByRole('button', { name: 'Assign role' }).click()

    const modal = app.getByRole('dialog')
    await expect(modal.getByText('Assign roles')).toBeVisible()

    await modal.getByRole('button', { name: 'System', exact: true }).click()
    await app.getByRole('option', { name: 'Project', exact: true }).click()

    // Select a project from the project dropdown
    await modal.getByRole('button', { name: 'Select a project...' }).click()
    const defaultOption = app.getByRole('option', { name: 'default' })
    await expect(defaultOption).toBeVisible({ timeout: 10_000 })
    await defaultOption.click()

    // Open role multi-select and pick a role
    await modal.getByPlaceholder('Search for roles...').fill('project-user')
    const roleOption = app.getByRole('option', { name: 'project-user' })
    await expect(roleOption).toBeVisible({ timeout: 10_000 })
    await roleOption.click()

    // Submit the assignment
    await modal.getByRole('button', { name: /Assign/ }).click()

    // Verify success alert
    await expect(app.getByText('Role assigned')).toBeVisible({ timeout: 15_000 })

    // Verify the assignment appears in the table
    await expect(app.getByRole('row', { name: /project-user/ })).toBeVisible()
  })

  test('assigns, displays, and revokes a system role', async ({ app }) => {
    await goToServiceAccountTab(app, sa, 'Assignments')
    await app.getByRole('button', { name: 'Assign role' }).click()

    const modal = app.getByRole('dialog')
    await expect(modal.getByText('Assign roles')).toBeVisible()
    await modal.getByPlaceholder('Search for roles...').click()
    await app.getByRole('option', { name: /^auditor Read-only/ }).click()
    await modal.getByRole('button', { name: /Assign/ }).click()

    await expect(app.getByText('Role assigned')).toBeVisible({ timeout: 15_000 })
    const assignmentActions = app.getByRole('button', { name: 'Actions for auditor (System)' })
    await expect(assignmentActions).toBeVisible()
    await assignmentActions.click()
    await app.getByRole('menuitem', { name: /Unassign/ }).click()
    const dialog = app.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Unassign role' }).click()

    await expect(app.getByRole('row', { name: /auditor/ })).not.toBeVisible({ timeout: 15_000 })
  })
})
