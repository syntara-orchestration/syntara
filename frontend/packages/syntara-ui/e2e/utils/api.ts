/**
 * API-based resource utilities for E2E test setup/teardown.
 *
 * Uses page.request (shares the browser's auth cookies/headers) to create
 * and clean up resources via the API — faster and more reliable than
 * UI-based setup, especially for fixtures.
 */
import { expect, type Page } from '@playwright/test'

import { appBaseUrl } from '../fixtures'

/** Get the API base URL (proxied through the UI server) */
function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, appBaseUrl).toString()
}

const AUTH_ATTEMPTS = 3
const AUTH_RETRY_DELAY = 500

/**
 * Authenticate via the API and return an access token.
 *
 * Every API setup helper funnels through here, so a single refused or timed-out
 * login on a loaded cluster fails the whole test before it starts. Retry the
 * transient cases; a 4xx means the credentials are genuinely wrong, so give up
 * immediately rather than burning the delay three times over.
 */
export async function getAuthToken(app: Page): Promise<string | null> {
  const password = process.env.SYNTARA_E2E_PASSWORD

  for (let attempt = 1; attempt <= AUTH_ATTEMPTS; attempt++) {
    try {
      const resp = await app.request.post(apiUrl('/auth/login'), {
        data: { username: 'admin', password: password ?? 'mock' },
      })
      if (resp.ok()) {
        const body = (await resp.json()) as { access_token?: string }
        if (body.access_token) return body.access_token
      } else if (resp.status() >= 400 && resp.status() < 500) {
        return null
      }
    } catch {
      // Network-level failure — fall through to the retry
    }
    if (attempt < AUTH_ATTEMPTS) await app.waitForTimeout(AUTH_RETRY_DELAY)
  }

  return null
}

/** Make an authenticated API request */
export async function apiRequest(
  app: Page,
  method: 'get' | 'post' | 'patch' | 'delete',
  path: string,
  options?: { data?: unknown; token?: string }
) {
  const token = options?.token ?? (await getAuthToken(app))
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  if (method === 'get') {
    return app.request.get(apiUrl(path), { headers })
  }
  if (method === 'post') {
    return app.request.post(apiUrl(path), { headers, data: options?.data })
  }
  if (method === 'patch') {
    return app.request.patch(apiUrl(path), { headers, data: options?.data })
  }
  return app.request.delete(apiUrl(path), { headers })
}

/**
 * Ensure a project exists and return its ID.
 * Lists projects first; creates one if missing. Returns null if API is unavailable.
 */
export async function ensureProject(app: Page, name = 'default'): Promise<{ id: string; name: string } | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const listResp = await apiRequest(app, 'get', '/projects', { token })
    if (!listResp.ok()) return null

    const body = (await listResp.json()) as { resources: Array<{ id: string; name: string }> }
    const existing = body.resources.find((p) => p.name === name)
    if (existing) return existing

    const createResp = await apiRequest(app, 'post', '/projects', {
      token,
      data: { name, description: `E2E test project: ${name}` },
    })
    if (createResp.ok()) {
      return (await createResp.json()) as { id: string; name: string }
    }
    // API creation blocked (e.g. RBAC 403) — project will be created via UI
    return null
  } catch {
    return null
  }
}

/**
 * Create a credential via the API. Returns the credential ID or null.
 */
export async function createCredentialViaApi(
  app: Page,
  options: { name: string; projectId: string; typeId?: string }
): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const typesResp = await apiRequest(app, 'get', '/credential_types', { token })
    if (!typesResp.ok()) return null

    const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
    const targetType =
      options.typeId ?? types.resources?.find((t) => t.name.includes('Bearer'))?.id ?? types.resources?.[0]?.id
    if (!targetType) return null

    const createResp = await apiRequest(app, 'post', '/credentials', {
      token,
      data: {
        name: options.name,
        credential_type_id: targetType,
        project_id: options.projectId,
        inputs: { token: 'e2e-test-token' },
      },
    })
    if (!createResp.ok()) return null
    const cred = (await createResp.json()) as { id?: string }
    return cred.id ?? null
  } catch {
    return null
  }
}

/**
 * Delete a credential via the API (best-effort cleanup).
 */
export async function deleteCredentialViaApi(app: Page, credentialId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) {
      await apiRequest(app, 'delete', `/credentials/${credentialId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

/**
 * List credentials by name via the authenticated API.
 * Returns matching credentials for cleanup purposes.
 */
export async function listCredentialsByName(app: Page, name: string): Promise<Array<{ id: string }>> {
  try {
    const token = await getAuthToken(app)
    if (!token) return []

    const resp = await apiRequest(app, 'get', `/credentials?name=${encodeURIComponent(name)}`, {
      token,
    })
    if (!resp.ok()) return []

    const body = (await resp.json()) as { resources?: Array<{ id: string }> }
    return body.resources ?? []
  } catch {
    return []
  }
}

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

/** Find a builtin group by name (case-insensitive). */
export async function findBuiltinGroupByName(app: Page, name: string): Promise<GroupResource | null> {
  const groups = await listAllGroups(app)
  const normalized = name.toLowerCase()
  return groups.find((g) => g.is_builtin && g.name?.toLowerCase() === normalized) ?? null
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

/** Create a role assignment via the API. Returns the assignment or null. */
export async function createRoleAssignmentViaApi(
  app: Page,
  options: { principal_id?: string; group_id?: string; role_name: string }
): Promise<{ id: string } | null> {
  const token = await getAuthToken(app)
  if (!token) return null
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

type WorkflowStepDef = { id: string; type: string; name?: string; parameters: Record<string, unknown> }
type WorkflowEdgeDef = { from: string; to: string; from_port?: string }

/** Create a workflow via the API. Returns the new workflow ID. */
export async function createWorkflowViaApi(
  app: Page,
  name: string,
  triggers: WorkflowStepDef[],
  nodes: WorkflowStepDef[] = [],
  edges: WorkflowEdgeDef[] = []
): Promise<{
  /** UUID of the created workflow. */
  id: string
  /** Version number of the initial draft, as returned by POST /workflows (`current_version`). Pass to `publishWorkflowViaApi` to avoid a separate GET. */
  versionNumber: number
}> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('createWorkflowViaApi: could not obtain auth token')
  const project = await ensureProject(app)
  if (!project) throw new Error('createWorkflowViaApi: could not ensure project')
  const resp = await apiRequest(app, 'post', '/workflows', {
    token,
    data: {
      name,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers,
        nodes,
        edges,
      },
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /workflows returned ${resp.status()}: ${body}`)
  }
  const body = (await resp.json()) as { id: string; current_version: number }
  return { id: body.id, versionNumber: body.current_version }
}

/** Publish a specific version of a workflow via the API. */
export async function publishWorkflowViaApi(
  app: Page,
  workflowId: string,
  /** Pass the value from `createWorkflowViaApi` to skip the extra GET. When omitted, the current version is fetched first. */
  versionNumber?: number
): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('publishWorkflowViaApi: could not obtain auth token')

  if (versionNumber === undefined) {
    const getResp = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    if (!getResp.ok()) {
      const body = await getResp.text().catch(() => '(unreadable)')
      throw new Error(`GET /workflows/${workflowId} returned ${getResp.status()}: ${body}`)
    }
    versionNumber = ((await getResp.json()) as { version: { version: number } }).version.version
  }

  const publishResp = await apiRequest(app, 'post', `/workflows/${workflowId}/versions/${versionNumber}/publish`, {
    token,
    data: {},
  })
  if (!publishResp.ok()) {
    const body = await publishResp.text().catch(() => '(unreadable)')
    throw new Error(
      `POST /workflows/${workflowId}/versions/${versionNumber}/publish returned ${publishResp.status()}: ${body}`
    )
  }
}

/**
 * API equivalent of `createBasicWorkflow` — manual trigger + script action.
 * Prefer this for arrange/cleanup; keep UI creation when the test asserts create UX.
 */
export async function createBasicWorkflowViaApi(
  app: Page,
  name: string,
  actionName = 'Script'
): Promise<{ id: string; name: string; versionNumber: number }> {
  const { id, versionNumber } = await createWorkflowViaApi(
    app,
    name,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'action_1',
        type: 'script',
        name: actionName,
        parameters: { language: 'python', code: 'print("hello")' },
      },
    ],
    [{ from: 'trigger_1', to: 'action_1' }]
  )
  return { id, name, versionNumber }
}

/** Look up a workflow ID by exact name (best-effort). */
export async function findWorkflowIdByName(app: Page, name: string): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null
    const resp = await apiRequest(app, 'get', `/workflows?name[contains]=${encodeURIComponent(name)}&limit=50`, {
      token,
    })
    if (!resp.ok()) return null
    const body = (await resp.json()) as { resources?: Array<{ id: string; name: string }> }
    return body.resources?.find((workflow) => workflow.name === name)?.id ?? null
  } catch {
    return null
  }
}

/** Delete a workflow by ID via the API (best-effort cleanup). */
export async function deleteWorkflowViaApi(app: Page, workflowId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/workflows/${workflowId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}

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

/**
 * Poll an execution's status via the API until it matches one of the expected values.
 * Retries every 1s until timeout (default 90s). Used to wait for Temporal state
 * transitions (e.g. "running", "paused", terminal statuses) without relying on UI updates.
 */
export async function pollExecutionStatus(
  app: Page,
  executionId: string,
  expectedStatuses: string[],
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  await expect(async () => {
    const resp = await apiRequest(app, 'get', `/executions/${executionId}`, { token })
    const exec = (await resp.json()) as { status: string }
    expect(expectedStatuses).toContain(exec.status)
  }).toPass({ timeout: options?.timeout ?? 90_000, intervals: [1_000] })
}

/**
 * Poll the approvals API until an approval with the given name is visible in the listing.
 * Use this after `pollExecutionStatus` reaches "paused" to guard against the brief async
 * gap between the execution being paused and the approval record being queryable.
 */
export async function pollApprovalVisible(
  app: Page,
  approvalName: string,
  options?: { token?: string; timeout?: number }
): Promise<void> {
  const token = options?.token ?? (await getAuthToken(app)) ?? undefined
  // The /approvals endpoint does not support name filtering — scan pending approvals by name.
  await expect(async () => {
    const resp = await apiRequest(app, 'get', '/approvals?status=pending&limit=100', { token })
    const body = (await resp.json()) as { resources?: Array<{ name: string }> }
    const found = body.resources?.some((r) => r.name === approvalName)
    expect(found).toBe(true)
  }).toPass({ timeout: options?.timeout ?? 30_000, intervals: [1_000] })
}
