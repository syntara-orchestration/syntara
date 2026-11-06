/**
 * RBAC & identity API helpers for E2E test setup/teardown.
 *
 * Covers users, groups, identity providers, policies, roles,
 * role assignments, and service accounts.
 */
import type { Page } from '../fixtures'

import { apiRequest, ensureProject, getAuthToken } from './api-core'

// ---------------------------------------------------------------------------
// Groups
// ---------------------------------------------------------------------------

export type GroupResource = {
  id: string
  name?: string
  is_builtin?: boolean
}

/**
 * List all groups via paginated API (mock API and real backend).
 */
export async function listAllGroups(app: Page): Promise<GroupResource[]> {
  try {
    const token = await getAuthToken(app)
    if (!token) return []

    const collected: GroupResource[] = []
    let cursor: string | undefined
    do {
      const path = cursor ? `/groups?limit=100&cursor=${encodeURIComponent(cursor)}` : '/groups?limit=100'
      const resp = await apiRequest(app, 'get', path, { token })
      if (!resp.ok()) return collected

      const body = (await resp.json()) as {
        resources?: GroupResource[]
        next?: string | null
      }
      collected.push(...(body.resources ?? []))
      cursor = body.next ?? undefined
    } while (cursor)

    return collected
  } catch {
    return []
  }
}

/** Create a group via the API. Returns the group ID or null. */
export async function createGroupViaApi(
  app: Page,
  options: { name: string; description?: string }
): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const resp = await apiRequest(app, 'post', '/groups', {
      token,
      data: { name: options.name, description: options.description ?? `E2E group: ${options.name}` },
    })
    if (!resp.ok()) return null
    const group = (await resp.json()) as { id?: string }
    return group.id ?? null
  } catch {
    return null
  }
}

/** Delete a group via the API (best-effort cleanup). */
export async function deleteGroupViaApi(app: Page, groupId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) {
      await apiRequest(app, 'delete', `/groups/${groupId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

/** Find a builtin group by name (case-insensitive). */
export async function findBuiltinGroupByName(app: Page, name: string): Promise<GroupResource | null> {
  const groups = await listAllGroups(app)
  const normalized = name.toLowerCase()
  return groups.find((g) => g.is_builtin && g.name?.toLowerCase() === normalized) ?? null
}

// ---------------------------------------------------------------------------
// Identity Providers
// ---------------------------------------------------------------------------

export type IdentityProviderResource = {
  id: string
  name?: string
  configuration?: {
    group_jmespath_expression?: string | null
    group_mapping_entries?: Array<{ idp_group_value: string; mapped_group_id: string }>
    claim_mapping?: Record<string, string | null>
  }
}

/** Create an identity provider via the API. Returns the provider or null. */
export async function createIdentityProviderViaApi(
  app: Page,
  body: {
    name: string
    enabled?: boolean
    configuration: IdentityProviderResource['configuration'] & Record<string, unknown>
  }
): Promise<IdentityProviderResource | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const resp = await apiRequest(app, 'post', '/identity_providers', {
      token,
      data: {
        name: body.name,
        enabled: body.enabled ?? true,
        configuration: body.configuration,
      },
    })
    if (!resp.ok()) return null
    return (await resp.json()) as IdentityProviderResource
  } catch {
    return null
  }
}

/** Delete an identity provider via the API (best-effort cleanup). */
export async function deleteIdentityProviderViaApi(app: Page, providerId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) {
      await apiRequest(app, 'delete', `/identity_providers/${providerId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

/** Find an identity provider by exact name. */
export async function findIdentityProviderByName(app: Page, name: string): Promise<IdentityProviderResource | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const resp = await apiRequest(app, 'get', '/identity_providers?limit=100', { token })
    if (!resp.ok()) return null

    const body = (await resp.json()) as { resources?: IdentityProviderResource[] }
    return body.resources?.find((p) => p.name === name) ?? null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

/** Create a user via the API. Returns the user or null. */
export async function createUserViaApi(
  app: Page,
  options: { username: string; email?: string; password: string }
): Promise<{ id: string; username: string } | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null
    const resp = await apiRequest(app, 'post', '/users', {
      token,
      data: {
        username: options.username,
        email: options.email ?? `${options.username}@e2e.example.com`,
        first_name: options.username,
        password: options.password,
      },
    })
    if (!resp.ok()) {
      const body = await resp.text().catch(() => '(unreadable)')
      throw new Error(`POST /users returned ${resp.status()}: ${body}`)
    }
    return (await resp.json()) as { id: string; username: string }
  } catch (e) {
    if (e instanceof Error && e.message.startsWith('POST /users')) throw e
    return null
  }
}

/** Delete a user via the API (best-effort cleanup). */
export async function deleteUserViaApi(app: Page, userId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/users/${userId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------

/** Create a policy via the API. Returns the policy or null. */
export async function createPolicyViaApi(
  app: Page,
  options: { name: string; actions: string[] }
): Promise<{ id: string; name: string } | null> {
  const token = await getAuthToken(app)
  if (!token) return null
  const resp = await apiRequest(app, 'post', '/policies', {
    token,
    data: {
      name: options.name,
      statements: [{ effect: 'allow', actions: options.actions, scope: 'any' }],
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /policies returned ${resp.status()}: ${body}`)
  }
  return (await resp.json()) as { id: string; name: string }
}

/** Delete a policy via the API (best-effort cleanup). */
export async function deletePolicyViaApi(app: Page, policyId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/policies/${policyId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

/** Create a role via the API. Returns the role or null. */
export async function createRoleViaApi(
  app: Page,
  options: { name: string; policies: string[] }
): Promise<{ id: string; name: string } | null> {
  const token = await getAuthToken(app)
  if (!token) return null
  const resp = await apiRequest(app, 'post', '/roles', {
    token,
    data: { name: options.name, policies: options.policies },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /roles returned ${resp.status()}: ${body}`)
  }
  return (await resp.json()) as { id: string; name: string }
}

/** Delete a role via the API (best-effort cleanup). */
export async function deleteRoleViaApi(app: Page, roleId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/roles/${roleId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

// ---------------------------------------------------------------------------
// Role Assignments
// ---------------------------------------------------------------------------

/** Create a role assignment via the API. Throws on missing token or HTTP failure. */
export async function createRoleAssignmentViaApi(
  app: Page,
  options: { principal_id?: string; group_id?: string; role_name: string }
): Promise<{ id: string }> {
  const token = await getAuthToken(app)
  if (!token) throw new Error(`createRoleAssignmentViaApi: could not obtain auth token for ${options.role_name}`)
  const resp = await apiRequest(app, 'post', '/role_assignments', {
    token,
    data: options,
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /role_assignments returned ${resp.status()}: ${body}`)
  }
  return (await resp.json()) as { id: string }
}

/** Delete a role assignment via the API (best-effort cleanup). */
export async function deleteRoleAssignmentViaApi(app: Page, assignmentId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/role_assignments/${assignmentId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

// ---------------------------------------------------------------------------
// Service Accounts
// ---------------------------------------------------------------------------

/** Create a service account via the API. Returns the created resource. */
export async function createServiceAccountViaApi(app: Page, name: string): Promise<{ id: string; name: string }> {
  const project = await ensureProject(app)
  if (!project) throw new Error('createServiceAccountViaApi: could not ensure project')

  const resp = await apiRequest(app, 'post', '/service_accounts', {
    data: { name, description: 'E2E test service account', project_id: project.id },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /service_accounts returned ${resp.status()}: ${body}`)
  }
  const body = (await resp.json()) as { id: string; name: string }
  return body
}

/** Delete a service account by ID via the API (best-effort cleanup). */
export async function deleteServiceAccountViaApi(app: Page, serviceAccountId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/service_accounts/${serviceAccountId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}
