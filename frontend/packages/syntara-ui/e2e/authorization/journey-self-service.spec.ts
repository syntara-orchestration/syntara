/**
 * TC-2.2: Self-service delegation journey.
 *
 * Admin sets up a project with resources, creates a delegation-manager role
 * with role-assignment permissions, and assigns it to a team lead. The team
 * lead independently onboards a new team member, verifies their access, and
 * later revokes it — all without admin intervention.
 *
 * Requires a live backend — skipped when SYNTARA_E2E_PASSWORD is not set.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { apiRequest, createCredentialViaApi, getAuthToken } from '../utils/api'

import {
  assignProjectRoleApi,
  createProjectRoleApi,
  deleteProjectApi,
  deleteProjectRoleAssignmentApi,
  deleteUserApi,
  expect,
  listProjectRoleAssignments,
  loginAsUserApi,
  loginViaUI,
  logoutViaUI,
  selectProject,
  toAppUrl,
  tryAssignSystemRole,
  tryCreateUser,
  tryCreateWorkflow,
  createWorkflowApi,
  createUserApi,
} from './fixtures'

const isLiveBackend = !!process.env.SYNTARA_E2E_PASSWORD

test.describe('Self-service delegation journey', () => {
  test.skip(!isLiveBackend, 'Journey tests require a live backend with SYNTARA_E2E_PASSWORD')

  test('TC-2.2: team lead delegates and revokes access for newcomer', async ({ app }) => {
    const suffix = buildUniqueName('j2')

    const adminToken = (await getAuthToken(app))!
    const adminPassword = process.env.SYNTARA_E2E_PASSWORD!

    const createdUserIds: string[] = []
    let projectId: string | undefined

    try {
      // 1. Admin creates project + resources
      const projResp = await apiRequest(app, 'post', '/projects', {
        token: adminToken,
        data: { name: `platform-${suffix}` },
      })
      const project = (await projResp.json()) as { id: string; name: string }
      projectId = project.id

      const wf = await createWorkflowApi(app, `health-check-${suffix}`, project.id)

      await createCredentialViaApi(app, { name: `api-token-${suffix}`, projectId: project.id })

      // 2. Create delegation-manager role
      const delegationPolicies = [
        'role-assignment:assign:project',
        'role-assignment:read:project',
        'role-assignment:revoke:project',
        'project:read:project',
        'workflow:read:project',
        'credential:read:project',
      ]
      const delegationRole = `delegation-mgr-${suffix}`
      await createProjectRoleApi(app, project.id, delegationRole, delegationPolicies)

      // 3. Create team lead and assign delegation role
      const teamLead = await createUserApi(app, `lead-${suffix}`)
      createdUserIds.push(teamLead.id)

      await assignProjectRoleApi(app, project.id, teamLead.id, delegationRole)

      // 4. Admin verifies setup in UI
      await loginViaUI(app, 'admin', adminPassword)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // 5. Team lead logs in and verifies access
      await logoutViaUI(app)
      await loginViaUI(app, teamLead.username)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // Team lead cannot create workflows (no workflow:create) — fresh token to avoid expiry
      let teamLeadToken = await loginAsUserApi(app, teamLead.username)
      const tlCreate = await tryCreateWorkflow(app, teamLeadToken, `tl-fail-${suffix}`, project.id)
      expect(tlCreate.ok).toBe(false)
      expect([401, 403, 404]).toContain(tlCreate.status)

      // Team lead cannot create users (no user:create)
      const tlUser = await tryCreateUser(app, teamLeadToken, `tl-user-fail-${suffix}`)
      expect(tlUser.ok).toBe(false)
      expect([401, 403, 404]).toContain(tlUser.status)

      // 6. Admin creates new hire (team lead can't)
      const newHire = await createUserApi(app, `newhire-${suffix}`)
      createdUserIds.push(newHire.id)

      // 7. Team lead assigns project-user to new hire — refresh token
      teamLeadToken = await loginAsUserApi(app, teamLead.username)
      const assignment = await assignProjectRoleApi(app, project.id, newHire.id, 'project-user', teamLeadToken)

      // 8. New hire logs in and sees the workflow
      const newHireToken = await loginAsUserApi(app, newHire.username)

      await logoutViaUI(app)
      await loginViaUI(app, newHire.username)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // New hire can create workflows (project-user allows CRUD)
      const nhCreate = await tryCreateWorkflow(app, newHireToken, `newhire-wf-${suffix}`, project.id)
      expect(nhCreate.ok).toBe(true)

      // 9. Team lead lists assignments and sees new hire — refresh token
      teamLeadToken = await loginAsUserApi(app, teamLead.username)
      const assignments = await listProjectRoleAssignments(app, teamLeadToken, project.id)
      const nhAssignment = assignments.find(
        (a) => a.principal_name === newHire.username && a.role_name === 'project-user'
      )
      expect(nhAssignment).toBeTruthy()

      // 10. Team lead revokes new hire's access
      await deleteProjectRoleAssignmentApi(app, teamLeadToken, project.id, assignment.id)

      // 11. New hire can no longer create workflows — fresh token to verify real-time revocation
      const revokedToken = await loginAsUserApi(app, newHire.username)
      const nhFail = await tryCreateWorkflow(app, revokedToken, `nh-fail-${suffix}`, project.id)
      expect(nhFail.ok).toBe(false)
      expect([401, 403, 404]).toContain(nhFail.status)

      // 12. New hire can still log in
      await logoutViaUI(app)
      await loginViaUI(app, newHire.username)
      await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 15_000 })

      // 13. Team lead cannot assign system-level admin role
      const tlAdmin = await tryAssignSystemRole(app, teamLeadToken, newHire.id, 'admin')
      expect(tlAdmin.ok).toBe(false)
      expect([401, 403, 404]).toContain(tlAdmin.status)
    } finally {
      for (const userId of createdUserIds) await deleteUserApi(app, userId)
      if (projectId) await deleteProjectApi(app, projectId)
    }
  })
})
