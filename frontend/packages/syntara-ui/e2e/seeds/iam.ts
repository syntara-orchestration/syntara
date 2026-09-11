/**
 * IAM seed helpers for E2E tests running against a real backend.
 *
 * Creates users, roles, policies, role assignments, and groups via the API.
 * Falls back to mock credentials (password: "mock") when SYNTARA_E2E_PASSWORD is not set.
 *
 * Each spec file should use a unique prefix (via buildUniqueName) to avoid
 * conflicts with parallel Playwright workers.
 */
import { type Page } from '../fixtures'
import { apiRequest, getAuthToken } from '../utils/api'

export type SeededUser = {
  id: string
  username: string
}

export type SeededRole = {
  id: string
  name: string
}

export type SeededPolicy = {
  id: string
  name: string
  projectId: string
}

export type SeededRoleAssignment = {
  id: string
  projectId: string
}

export type SeededGroup = {
  id: string
  name: string
  createdByUs: boolean
}

export async function createUserViaApi(page: Page, options: { username: string; token?: string }): Promise<SeededUser> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw new Error(`createUserViaApi: could not obtain auth token for ${options.username}`)

  const resp = await apiRequest(page, 'post', '/users', {
    token,
    data: {
      username: options.username,
      email: `${options.username}@example.com`,
      first_name: `E2E ${options.username}`,
      password: 'e2e-test-password-123!',
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw new Error(`createUserViaApi failed for ${options.username}: HTTP ${resp.status()} ${body}`)
  }
  const user = (await resp.json()) as { id: string; username: string }
  return { id: user.id, username: user.username }
}

export async function deleteUserViaApi(page: Page, userId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/users/${userId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

export async function createRoleViaApi(
  page: Page,
  options: { name: string; policies?: string[]; token?: string }
): Promise<SeededRole> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw new Error(`createRoleViaApi: could not obtain auth token for ${options.name}`)

  // System roles require ≥1 global policy. Project-scoped policies 422; mock accepted [].
  const policies = options.policies?.length ? options.policies : ['workflow:read:any']

  const resp = await apiRequest(page, 'post', '/roles', {
    token,
    data: {
      name: options.name,
      description: 'E2E test role',
      policies,
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw new Error(`createRoleViaApi failed for ${options.name}: HTTP ${resp.status()} ${body}`)
  }
  const role = (await resp.json()) as { id: string; name: string }
  return { id: role.id, name: role.name }
}

export async function deleteRoleViaApi(page: Page, roleId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/roles/${roleId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

export async function createPolicyViaApi(
  page: Page,
  projectId: string,
  options: { name: string; token?: string }
): Promise<SeededPolicy> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw new Error(`createPolicyViaApi: could not obtain auth token for ${options.name}`)

  const resp = await apiRequest(page, 'post', `/projects/${projectId}/policies`, {
    token,
    data: {
      name: options.name,
      description: 'E2E test policy',
      statements: [{ effect: 'allow', scope: 'project', actions: ['workflow:read', 'workflow:create'] }],
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw new Error(`createPolicyViaApi failed for ${options.name}: HTTP ${resp.status()} ${body}`)
  }
  const policy = (await resp.json()) as { id: string; name: string }
  return { id: policy.id, name: policy.name, projectId }
}

export async function deletePolicyViaApi(page: Page, projectId: string, policyId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/projects/${projectId}/policies/${policyId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

export async function createRoleAssignmentViaApi(
  page: Page,
  projectId: string,
  options: { userId: string; roleName: string; token?: string }
): Promise<SeededRoleAssignment> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw new Error(`createRoleAssignmentViaApi: could not obtain auth token for ${options.roleName}`)

  const resp = await apiRequest(page, 'post', `/projects/${projectId}/role_assignments`, {
    token,
    data: {
      principal_id: options.userId,
      role_name: options.roleName,
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw new Error(`createRoleAssignmentViaApi failed for ${options.roleName}: HTTP ${resp.status()} ${body}`)
  }
  const assignment = (await resp.json()) as { id: string }
  return { id: assignment.id, projectId }
}

export async function deleteRoleAssignmentViaApi(page: Page, projectId: string, assignmentId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/projects/${projectId}/role_assignments/${assignmentId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

/**
 * Ensure a group exists by name. Tries to find it first, creates if not found.
 * Returns the group info and whether we created it (for conditional cleanup).
 */
export async function ensureGroupExists(page: Page, groupName: string): Promise<SeededGroup> {
  const token = await getAuthToken(page)
  if (!token) throw new Error(`ensureGroupExists: could not obtain auth token for ${groupName}`)

  const listResp = await apiRequest(page, 'get', '/groups', { token })
  if (listResp.ok()) {
    const body = (await listResp.json()) as { resources?: Array<{ id: string; name: string }> }
    const existing = body.resources?.find((g) => g.name === groupName)
    if (existing) {
      return { id: existing.id, name: existing.name, createdByUs: false }
    }
  }

  const createResp = await apiRequest(page, 'post', '/groups', {
    token,
    data: { name: groupName, description: `E2E seed group: ${groupName}` },
  })
  if (!createResp.ok()) {
    const body = await createResp.text().catch(() => '')
    throw new Error(`ensureGroupExists failed to create ${groupName}: HTTP ${createResp.status()} ${body}`)
  }
  const group = (await createResp.json()) as { id: string; name: string }
  return { id: group.id, name: group.name, createdByUs: true }
}

export async function deleteGroupViaApi(page: Page, groupId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/groups/${groupId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}
