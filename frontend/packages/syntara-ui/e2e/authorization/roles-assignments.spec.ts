/**
 * E2E Tests: Roles & Assignments (AAP-76528)
 *
 * Tests verifying Access Management UI visibility.
 *
 * TC-1.1: Admin sees Access Management with Roles tab and Role Assignments tab.
 * TC-1.2: Admin sees system roles with "System" scope in the Roles list.
 * TC-1.3: SA role assignment renders "Service Account" label in assignments table.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import {
  createServiceAccountViaApi,
  deleteRoleAssignmentViaApi,
  deleteServiceAccountViaApi,
  ensureProject,
} from '../utils/api'

import { assignProjectRoleApi, expect, toAppUrl } from './fixtures'

const ACCESS_URL = '/system-administration/access-management'

test.describe('AAP-76528: Roles & Assignments', () => {
  test('TC-1.1: Admin sees Roles tab and Role Assignments tab in Access Management', async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
    await expect(app.getByRole('tab', { name: /^Roles$/i })).toBeVisible()
    await expect(app.getByRole('tab', { name: /Assignments/i })).toBeVisible()
    await app.getByRole('tab', { name: /Assignments/i }).click()
    await expect(app.getByRole('tab', { name: /Assignments/i })).toBeVisible()
  })

  test('TC-1.2: Admin sees system roles with "System" scope in Roles list', async ({ app }) => {
    await app.goto(toAppUrl(`${ACCESS_URL}/roles`))
    await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
    await app.getByRole('tab', { name: /^Roles$/i }).click()
    const table = app.getByRole('grid')
    await expect(table.getByRole('row').filter({ hasText: 'System' }).first()).toBeVisible() // eslint-disable-line no-restricted-properties -- multiple rows may have "System" scope; asserting any is present
  })

  test('TC-1.3: SA role assignment renders "Service Account" label in assignments table', async ({ app }) => {
    const saName = buildUniqueName('e2e-sa-label')
    const sa = await createServiceAccountViaApi(app, saName)
    const project = await ensureProject(app)
    if (!project) throw new Error('Could not ensure project for SA assignment')

    const assignment = await assignProjectRoleApi({
      page: app,
      projectId: project.id,
      userId: sa.id,
      roleName: 'project-user',
    })
    try {
      await app.goto(toAppUrl(`${ACCESS_URL}/assignments`))
      await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()

      const table = app.getByRole('grid', { name: 'Role assignments' })
      const saRow = table.getByRole('row').filter({ hasText: saName })
      await expect(saRow).toBeVisible()
      await expect(saRow.getByText('Service account')).toBeVisible()
    } finally {
      await deleteRoleAssignmentViaApi(app, assignment.id)
      await deleteServiceAccountViaApi(app, sa.id)
    }
  })
})
