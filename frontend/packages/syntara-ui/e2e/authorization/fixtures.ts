/**
 * Authorization test fixtures.
 *
 * Creates real users with real roles and policies via the API so that
 * the backend's can_i endpoint drives UI visibility decisions.
 */
import { randomUUID } from 'node:crypto'

import { type Page } from '@playwright/test'

import { expect, appBaseUrl, toAppUrl } from '../fixtures'
import { APP_TITLE } from '../helpers/appTitle'
import {
  createUserViaApi,
  deleteUserViaApi,
  createPolicyViaApi,
  deletePolicyViaApi,
  createRoleViaApi,
  deleteRoleViaApi,
  createRoleAssignmentViaApi,
  deleteRoleAssignmentViaApi,
  apiRequest,
  getAuthToken,
} from '../utils/api'

// ---------------------------------------------------------------------------
// Persona lifecycle
// ---------------------------------------------------------------------------

const E2E_TEST_PASSWORD = 'E2eTestP@ssw0rd!'

export type Persona = {
  userId: string
  username: string
  password: string
  policyId: string | null
  roleId: string | null
  assignmentId: string | null
}

/**
 * Create a test user with a custom role granting the specified permissions.
 * Uses the admin-authenticated API to:
 *   1. Create a policy with the given actions
 *   2. Create a role referencing that policy
 *   3. Create a user
 *   4. Assign the role to the user
 *
 * Returns a Persona for login and cleanup.
 */
export async function createPersona(app: Page, name: string, actions: string[]): Promise<Persona> {
  const policy = await createPolicyViaApi(app, {
    name: `${name}-policy`,
    actions,
  })
  if (!policy) throw new Error(`Failed to create policy for persona "${name}"`)

  const role = await createRoleViaApi(app, {
    name: `${name}-role`,
    policies: [policy.name],
  })
  if (!role) throw new Error(`Failed to create role for persona "${name}"`)

  const user = await createUserViaApi(app, {
    username: name,
    password: E2E_TEST_PASSWORD,
  })
  if (!user) throw new Error(`Failed to create user for persona "${name}"`)

  const assignment = await createRoleAssignmentViaApi(app, {
    principal_id: user.id,
    role_name: role.name,
  })
  if (!assignment) throw new Error(`Failed to assign role for persona "${name}"`)

  return {
    userId: user.id,
    username: user.username,
    password: E2E_TEST_PASSWORD,
    policyId: policy.id,
    roleId: role.id,
    assignmentId: assignment.id,
  }
}

/**
 * Create a test user with the builtin admin role (no custom policy needed).
 */
export async function createAdminPersona(app: Page, name: string): Promise<Persona> {
  const user = await createUserViaApi(app, {
    username: name,
    password: E2E_TEST_PASSWORD,
  })
  if (!user) throw new Error(`Failed to create admin user "${name}"`)

  const assignment = await createRoleAssignmentViaApi(app, {
    principal_id: user.id,
    role_name: 'admin',
  })
  if (!assignment) throw new Error(`Failed to assign admin role for "${name}"`)

  return {
    userId: user.id,
    username: user.username,
    password: E2E_TEST_PASSWORD,
    policyId: null,
    roleId: null,
    assignmentId: assignment.id,
  }
}

/**
 * Clean up a persona — deletes assignment, role, policy, user in reverse order.
 * Best-effort: swallows errors so cleanup doesn't mask test failures.
 */
export async function cleanupPersona(app: Page, persona: Persona): Promise<void> {
  if (persona.assignmentId) await deleteRoleAssignmentViaApi(app, persona.assignmentId)
  if (persona.roleId) await deleteRoleViaApi(app, persona.roleId)
  if (persona.policyId) await deletePolicyViaApi(app, persona.policyId)
  await deleteUserViaApi(app, persona.userId)
}

/**
 * Log in as a specific user via the UI login form.
 */
export async function loginAsUser(page: Page, persona: Pick<Persona, 'username' | 'password'>): Promise<void> {
  await page.goto(appBaseUrl)

  const loginHeading = page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })
  const mainNav = page.getByRole('navigation', { name: 'Main navigation' })
  await loginHeading.or(mainNav).waitFor({ timeout: 15_000 })

  if (await loginHeading.isVisible()) {
    const password = persona.password
    const localAccountToggle = page.getByRole('button', { name: 'Sign in using local account' })
    if (await localAccountToggle.isVisible()) await localAccountToggle.click()

    await page.getByLabel('Username').fill(persona.username)
    await page.getByRole('textbox', { name: 'Password' }).fill(password)
    await page.getByRole('button', { name: /^Log in( as administrator)?$/ }).click()
  }

  await expect(mainNav).toBeVisible({ timeout: 15_000 })
}

// ---------------------------------------------------------------------------
// Common permission action sets for personas
// ---------------------------------------------------------------------------

export const PERSONA_ACTIONS = {
  credentialsManager: [
    'credential:create',
    'credential:read',
    'credential:update',
    'credential:delete',
    'project:read',
  ],

  workflowManager: ['workflow:create', 'workflow:read', 'workflow:update', 'workflow:delete', 'project:read'],

  executionOperator: ['workflow:read', 'execution:run', 'execution:read', 'project:read'],

  approvalOperator: ['approval:read', 'approval:decide', 'project:read'],

  projectManager: ['project:create', 'project:read'],

  roleAssignmentManager: [
    'role-assignment:assign',
    'role-assignment:read',
    'role-assignment:revoke',
    'role:read',
    'project:read',
  ],

  userManager: ['user:create', 'user:read', 'user:update'],

  projectReader: ['workflow:read', 'credential:read', 'execution:read', 'project:read'],

  projectWriter: [
    'workflow:read',
    'workflow:create',
    'workflow:update',
    'credential:read',
    'execution:read',
    'project:read',
  ],
}

// ---------------------------------------------------------------------------
// Journey test helpers (TC-2.x)
// ---------------------------------------------------------------------------

const USER_PASSWORD = `E2e-${randomUUID()}!`

export async function loginViaUI(page: Page, username: string, password: string = USER_PASSWORD): Promise<void> {
  await page.goto(toAppUrl('/'))

  const loginHeading = page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })
  const mainNav = page.getByRole('navigation', { name: 'Main navigation' })
  await loginHeading.or(mainNav).waitFor({ timeout: 15_000 })

  if (await loginHeading.isVisible()) {
    const localAccountToggle = page.getByRole('button', { name: 'Sign in using local account' })
    if (await localAccountToggle.isVisible()) {
      await localAccountToggle.click()
    }

    await page.getByLabel('Username').fill(username)
    await page.getByRole('textbox', { name: 'Password' }).fill(password)
    await page.getByRole('button', { name: /^Log in( as administrator)?$/ }).click()
    await expect(mainNav).toBeVisible({ timeout: 15_000 })
  }
}

export async function logoutViaUI(page: Page): Promise<void> {
  // Clear the session programmatically instead of clicking the Logout button.
  // The UI logout triggers a POST to /auth/logout to revoke the HttpOnly cookie,
  // but the bootstrap refresh() can race it and re-authenticate before the cookie
  // is actually cleared — leaving the user still logged in.
  await page.context().clearCookies()
  await page.evaluate(() => localStorage.clear())
  await page.goto(toAppUrl('/'))
  await page.getByRole('heading', { name: `Log in to ${APP_TITLE}` }).waitFor({ timeout: 30_000 })
}

export async function loginAsUserApi(page: Page, username: string, password: string = USER_PASSWORD): Promise<string> {
  const resp = await apiRequest(page, 'post', '/auth/login', { data: { username, password } })
  if (!resp.ok()) throw new Error(`Login failed for ${username}: ${resp.status()}`)
  const body = (await resp.json()) as { access_token: string }
  return body.access_token
}

export async function createUserApi(page: Page, username: string): Promise<{ id: string; username: string }> {
  const token = await getAuthToken(page)
  if (!token) throw new Error('No admin token')
  const resp = await apiRequest(page, 'post', '/users', {
    token,
    data: {
      username,
      email: `${username}@example.com`,
      first_name: `E2E ${username}`,
      password: USER_PASSWORD,
    },
  })
  if (!resp.ok()) throw new Error(`Failed to create user ${username}: ${resp.status()}`)
  return (await resp.json()) as { id: string; username: string }
}

export async function deleteUserApi(page: Page, userId: string): Promise<void> {
  const token = await getAuthToken(page)
  if (!token) return
  await apiRequest(page, 'delete', `/users/${userId}`, { token })
}

export async function deleteProjectApi(page: Page, projectId: string): Promise<void> {
  const token = await getAuthToken(page)
  if (!token) return
  await apiRequest(page, 'delete', `/projects/${projectId}`, { token })
}

export async function createProjectRoleApi(
  page: Page,
  projectId: string,
  name: string,
  policies: string[]
): Promise<void> {
  const token = await getAuthToken(page)
  if (!token) throw new Error('No admin token')
  const resp = await apiRequest(page, 'post', `/projects/${projectId}/roles`, {
    token,
    data: { name, policies },
  })
  if (!resp.ok()) throw new Error(`Failed to create role ${name}: ${resp.status()}`)
}

export async function addGroupMemberApi(page: Page, groupId: string, userId: string): Promise<void> {
  const token = await getAuthToken(page)
  if (!token) throw new Error('No admin token')
  const resp = await apiRequest(page, 'post', `/groups/${groupId}/members`, {
    token,
    data: { user_id: userId },
  })
  if (!resp.ok()) throw new Error(`Failed to add member: ${resp.status()}`)
}

export async function assignProjectRoleApi({
  page,
  projectId,
  userId,
  roleName,
  token,
}: {
  page: Page
  projectId: string
  userId: string
  roleName: string
  token?: string
}): Promise<{ id: string }> {
  const t = token ?? (await getAuthToken(page))
  if (!t) throw new Error('No token')
  const resp = await apiRequest(page, 'post', `/projects/${projectId}/role_assignments`, {
    token: t,
    data: { principal_id: userId, role_name: roleName },
  })
  if (!resp.ok()) throw new Error(`Failed to assign role: ${resp.status()}`)
  return (await resp.json()) as { id: string }
}

export async function assignGroupProjectRoleApi(
  page: Page,
  projectId: string,
  groupId: string,
  roleName: string
): Promise<void> {
  const token = await getAuthToken(page)
  if (!token) throw new Error('No admin token')
  const resp = await apiRequest(page, 'post', `/projects/${projectId}/role_assignments`, {
    token,
    data: { group_id: groupId, role_name: roleName },
  })
  if (!resp.ok()) throw new Error(`Failed to assign group role: ${resp.status()}`)
}

export async function tryCreateWorkflow(
  page: Page,
  token: string,
  name: string,
  projectId: string
): Promise<{ ok: boolean; status: number }> {
  const resp = await apiRequest(page, 'post', '/workflows', {
    token,
    data: {
      name,
      project_id: projectId,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', parameters: {} }],
        nodes: [],
        edges: [],
      },
    },
  })
  return { ok: resp.ok(), status: resp.status() }
}

export async function tryRunExecution(
  page: Page,
  token: string,
  workflowId: string
): Promise<{ ok: boolean; status: number }> {
  const resp = await apiRequest(page, 'post', '/executions', {
    token,
    data: { workflow_id: workflowId, trigger_node_id: 'trigger_1' },
  })
  return { ok: resp.ok(), status: resp.status() }
}

export async function tryCreateCredential(
  page: Page,
  token: string,
  opts: { name: string; projectId: string; typeId: string; inputs: Record<string, string> }
): Promise<{ ok: boolean; status: number }> {
  const resp = await apiRequest(page, 'post', '/credentials', {
    token,
    data: {
      name: opts.name,
      project_id: opts.projectId,
      credential_type_id: opts.typeId,
      inputs: opts.inputs,
    },
  })
  return { ok: resp.ok(), status: resp.status() }
}

export async function tryCreateUser(
  page: Page,
  token: string,
  username: string
): Promise<{ ok: boolean; status: number }> {
  const resp = await apiRequest(page, 'post', '/users', {
    token,
    data: { username, email: `${username}@example.com`, first_name: `E2E ${username}`, password: USER_PASSWORD },
  })
  return { ok: resp.ok(), status: resp.status() }
}

export async function tryAssignSystemRole(
  page: Page,
  token: string,
  userId: string,
  roleName: string
): Promise<{ ok: boolean; status: number }> {
  const resp = await apiRequest(page, 'post', `/users/${userId}/role_assignments`, {
    token,
    data: { role_name: roleName },
  })
  return { ok: resp.ok(), status: resp.status() }
}

export async function listProjectRoleAssignments(
  page: Page,
  token: string,
  projectId: string
): Promise<Array<{ id: string; principal_name: string; role_name: string }>> {
  const resp = await apiRequest(page, 'get', `/projects/${projectId}/role_assignments`, { token })
  if (!resp.ok()) return []
  const body = (await resp.json()) as {
    resources: Array<{ id: string; principal_name: string; role_name: string }>
  }
  return body.resources ?? []
}

export async function deleteProjectRoleAssignmentApi(
  page: Page,
  token: string,
  projectId: string,
  assignmentId: string
): Promise<void> {
  await apiRequest(page, 'delete', `/projects/${projectId}/role_assignments/${assignmentId}`, { token })
}

export async function getCredentialTypesApi(page: Page): Promise<Array<{ id: string; name: string }>> {
  const token = await getAuthToken(page)
  if (!token) return []
  const resp = await apiRequest(page, 'get', '/credential_types', { token })
  if (!resp.ok()) return []
  const body = (await resp.json()) as { resources: Array<{ id: string; name: string }> }
  return body.resources ?? []
}

export async function createWorkflowApi(
  page: Page,
  name: string,
  projectId: string
): Promise<{ id: string; name: string }> {
  const token = await getAuthToken(page)
  if (!token) throw new Error('No admin token')
  const resp = await apiRequest(page, 'post', '/workflows', {
    token,
    data: {
      name,
      project_id: projectId,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', parameters: {} }],
        nodes: [],
        edges: [],
      },
    },
  })
  if (!resp.ok()) throw new Error(`Failed to create workflow: ${resp.status()}`)
  return (await resp.json()) as { id: string; name: string }
}

export async function selectProject(page: Page, projectName: string): Promise<void> {
  const input = page
    .getByRole('textbox', { name: 'Type to filter' })
    .or(page.getByPlaceholder('All projects'))
    .or(page.getByPlaceholder('Select a project'))
    .or(page.getByPlaceholder(projectName))
  await input.first().click()
  await input.first().fill(projectName)
  const option = page.getByRole('option', { name: projectName })
  if (await option.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await option.click()
  } else {
    await page.keyboard.press('Escape')
  }
}

export { expect, toAppUrl }
