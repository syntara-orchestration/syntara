/**
 * TC-2.1: New team onboarding journey.
 *
 * Admin creates a project with workflows and credentials, defines three custom
 * roles (reader, writer, operator), creates a team group with three members,
 * assigns the group a base reader role, then layers individual writer and
 * operator roles on specific members. Verifies each member's access via UI + API.
 *
 * Requires a live backend — skipped when SYNTARA_E2E_PASSWORD is not set.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'
import { deleteGroupViaApi, ensureGroupExists } from '../seeds/iam'
import { apiRequest, createCredentialViaApi, getAuthToken } from '../utils/api'

import {
  addGroupMemberApi,
  assignGroupProjectRoleApi,
  assignProjectRoleApi,
  createProjectRoleApi,
  deleteProjectApi,
  deleteUserApi,
  expect,
  getCredentialTypesApi,
  loginAsUserApi,
  loginViaUI,
  logoutViaUI,
  selectProject,
  toAppUrl,
  tryCreateCredential,
  tryCreateWorkflow,
  tryRunExecution,
  createWorkflowApi,
  createUserApi,
} from './fixtures'

const isLiveBackend = !!process.env.SYNTARA_E2E_PASSWORD

test.describe('Team onboarding journey', () => {
  test.skip(!isLiveBackend, 'Journey tests require a live backend with SYNTARA_E2E_PASSWORD')

  test('TC-2.1: full team onboarding with differentiated roles', async ({ app }) => {
    const suffix = buildUniqueName('j1')

    const adminToken = (await getAuthToken(app))!
    const adminPassword = process.env.SYNTARA_E2E_PASSWORD!

    const createdUserIds: string[] = []
    let projectId: string | undefined
    let groupId: string | undefined

    try {
      // 1. Create project via API
      const projResp = await apiRequest(app, 'post', '/projects', {
        token: adminToken,
        data: { name: `onboard-${suffix}` },
      })
      const project = (await projResp.json()) as { id: string; name: string }
      projectId = project.id

      // 2. Create workflow and credential
      const wf = await createWorkflowApi(app, `deploy-${suffix}`, project.id)

      await createCredentialViaApi(app, { name: `cred-${suffix}`, projectId: project.id })

      const credTypes = await getCredentialTypesApi(app)
      const anyCredType = credTypes[0]

      // 3. Create three roles
      const readerPolicies = [
        'workflow:read:project',
        'credential:read:project',
        'execution:read:project',
        'project:read:project',
      ]
      const writerPolicies = [...readerPolicies, 'workflow:create:project', 'workflow:update:project']
      const operatorPolicies = [...readerPolicies, 'execution:run:project']

      const readerRole = `reader-${suffix}`
      const writerRole = `writer-${suffix}`
      const operatorRole = `operator-${suffix}`

      await createProjectRoleApi(app, project.id, readerRole, readerPolicies)
      await createProjectRoleApi(app, project.id, writerRole, writerPolicies)
      await createProjectRoleApi(app, project.id, operatorRole, operatorPolicies)

      // 4. Create group + 3 users
      const group = await ensureGroupExists(app, `team-${suffix}`)
      if (!group) throw new Error('Failed to create group')
      groupId = group.id

      const alice = await createUserApi(app, `alice-${suffix}`)
      const bob = await createUserApi(app, `bob-${suffix}`)
      const carol = await createUserApi(app, `carol-${suffix}`)
      createdUserIds.push(alice.id, bob.id, carol.id)

      await addGroupMemberApi(app, group.id, alice.id)
      await addGroupMemberApi(app, group.id, bob.id)
      await addGroupMemberApi(app, group.id, carol.id)

      // 5. Assign roles: group gets reader, alice gets writer, bob gets operator
      await assignGroupProjectRoleApi(app, project.id, group.id, readerRole)
      await assignProjectRoleApi(app, project.id, alice.id, writerRole)
      await assignProjectRoleApi(app, project.id, bob.id, operatorRole)

      // 6. Admin verifies in UI
      await loginViaUI(app, 'admin', adminPassword)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // --- Alice: reader (group) + writer (direct) ---
      await logoutViaUI(app)
      await loginViaUI(app, alice.username)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // Alice can create workflows (writer role) — fresh token right before API calls
      const aliceToken = await loginAsUserApi(app, alice.username)
      const aliceCreate = await tryCreateWorkflow(app, aliceToken, `alice-wf-${suffix}`, project.id)
      expect(aliceCreate.ok).toBe(true)

      // Alice cannot run executions (no execution:run)
      const aliceRun = await tryRunExecution(app, aliceToken, wf.id)
      expect(aliceRun.ok).toBe(false)
      expect([401, 403, 404]).toContain(aliceRun.status)

      // --- Bob: reader (group) + operator (direct) ---
      await logoutViaUI(app)
      await loginViaUI(app, bob.username)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // Bob can trigger executions (operator role) — fresh token right before API calls
      const bobToken = await loginAsUserApi(app, bob.username)
      const bobRun = await tryRunExecution(app, bobToken, wf.id)
      expect(bobRun.ok).toBe(true)

      // Bob cannot create workflows (no workflow:create)
      const bobCreate = await tryCreateWorkflow(app, bobToken, `bob-fail-${suffix}`, project.id)
      expect(bobCreate.ok).toBe(false)
      expect([401, 403, 404]).toContain(bobCreate.status)

      // --- Carol: reader (group) only ---
      await logoutViaUI(app)
      await loginViaUI(app, carol.username)

      await app.goto(toAppUrl('/workflows'))
      await selectProject(app, project.name)
      await expect(app.getByRole('link', { name: wf.name, exact: true })).toBeVisible({ timeout: 10_000 })

      // Carol cannot create workflows — fresh token right before API calls
      const carolToken = await loginAsUserApi(app, carol.username)
      const carolCreate = await tryCreateWorkflow(app, carolToken, `carol-fail-${suffix}`, project.id)
      expect(carolCreate.ok).toBe(false)
      expect([401, 403, 404]).toContain(carolCreate.status)

      // Carol cannot run executions
      const carolRun = await tryRunExecution(app, carolToken, wf.id)
      expect(carolRun.ok).toBe(false)
      expect([401, 403, 404]).toContain(carolRun.status)

      // Carol cannot create credentials
      if (anyCredType) {
        const carolCred = await tryCreateCredential(app, carolToken, {
          name: `carol-fail-${suffix}`,
          projectId: project.id,
          typeId: anyCredType.id,
          inputs: { token: 'fail' },
        })
        expect(carolCred.ok).toBe(false)
        expect([401, 403, 404]).toContain(carolCred.status)
      }
    } finally {
      for (const userId of createdUserIds) await deleteUserApi(app, userId)
      if (groupId) await deleteGroupViaApi(app, groupId)
      if (projectId) await deleteProjectApi(app, projectId)
    }
  })
})
