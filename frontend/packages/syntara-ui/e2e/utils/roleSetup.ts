/**
 * Real-backend role user setup for permission-gating E2E tests.
 *
 * Creates three users (viewer, auditor, user) with role assignments that
 * mirror the mock API's can_i permission matrix (handlers.ts).
 *
 * - **auditor**: assigned the built-in "auditor" role directly.
 * - **viewer** / **user**: assigned a custom role built from the backend's
 *   built-in policy names (e.g. "workflow:read:any").
 *
 * Used by the worker-scoped `roleSetup` fixture in fixtures.ts so each
 * worker creates users once and reuses them across all tests.
 *
 * On the mock API path these are never called — the fixtures fall back to
 * mock-token interception instead.
 */
import { randomBytes } from 'node:crypto'

import type { APIRequestContext } from '@playwright/test'

import { buildUniqueName } from '../helpers/workflows'

function generatePassword(): string {
  return `E2e-${randomBytes(16).toString('hex')}!A1`
}

type RoleProfile = {
  /** Built-in role name to assign, OR null to create a custom role. */
  builtinRole: string | null
  /** Policy names for custom role creation (ignored when builtinRole is set). */
  policies: string[]
}

/**
 * Permission profiles that mirror the mock API roles.
 * Policy names use the backend's `resource:action:scope` convention.
 */
const ROLE_PROFILES: Record<string, RoleProfile> = {
  viewer: {
    builtinRole: null,
    policies: [
      'workflow:read:any',
      'execution:read:any',
      'approval:read:any',
      'credential:read:any',
      'integration:read:any',
    ],
  },
  auditor: {
    builtinRole: 'auditor',
    policies: [],
  },
  user: {
    builtinRole: null,
    policies: [
      'workflow:read:any',
      'execution:read:any',
      'approval:read:any',
      'credential:read:any',
      'integration:read:any',
      'user:read:any',
      'group:read:any',
      'role:read:any',
      'policy:read:any',
      'authz:query:any',
    ],
  },
}

export type RoleCredentials = {
  username: string
  password: string
}

export type RoleSetupResult = {
  credentials: Record<string, RoleCredentials>
  cleanup: () => Promise<void>
}

type ApiResource = { id: string }

async function postJson(
  request: APIRequestContext,
  url: string,
  headers: Record<string, string>,
  data: unknown
): Promise<ApiResource> {
  const resp = await request.post(url, { headers, data })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST ${url} returned ${resp.status()}: ${body}`)
  }
  return (await resp.json()) as ApiResource
}

/**
 * Create viewer/auditor/user accounts on the real backend with matching
 * role assignments.  Returns credentials for login and a cleanup function
 * that tears everything down in reverse order.
 */
export async function setupRoleUsers(request: APIRequestContext): Promise<RoleSetupResult> {
  const backendUrl = process.env.VITE_API_URL ?? process.env.SYNTARA_E2E_BASE_URL ?? 'http://localhost:8000'
  const adminPassword = process.env.SYNTARA_E2E_PASSWORD
  if (!adminPassword) throw new Error('SYNTARA_E2E_PASSWORD required for real-backend role setup')

  const loginResp = await request.post(`${backendUrl}/api/v1/auth/login`, {
    data: { username: 'admin', password: adminPassword },
  })
  if (!loginResp.ok()) throw new Error(`Admin login failed: ${loginResp.status()}`)
  const { access_token: token } = (await loginResp.json()) as { access_token: string }
  const headers = { Authorization: `Bearer ${token}` }
  const api = (path: string) => `${backendUrl}/api/v1${path}`

  const cleanupStack: Array<() => Promise<void>> = []
  const credentials: Record<string, RoleCredentials> = {}
  const password = generatePassword()

  try {
    for (const [role, profile] of Object.entries(ROLE_PROFILES)) {
      const prefix = buildUniqueName(`e2e-perm-${role}`)
      let assignRoleName: string

      if (profile.builtinRole) {
        assignRoleName = profile.builtinRole
      } else {
        const roleObj = await postJson(request, api('/roles'), headers, {
          name: `${prefix}-role`,
          policies: profile.policies,
        })
        cleanupStack.push(async () => {
          await request.delete(api(`/roles/${roleObj.id}`), { headers }).catch(() => {})
        })
        assignRoleName = `${prefix}-role`
      }

      const user = await postJson(request, api('/users'), headers, {
        username: prefix,
        email: `${prefix}@e2e.example.com`,
        first_name: `E2E ${role}`,
        password,
        group_names: [],
      })
      cleanupStack.push(async () => {
        await request.delete(api(`/users/${user.id}`), { headers }).catch(() => {})
      })

      const assignment = await postJson(request, api('/role_assignments'), headers, {
        principal_id: user.id,
        role_name: assignRoleName,
      })
      cleanupStack.push(async () => {
        await request.delete(api(`/role_assignments/${assignment.id}`), { headers }).catch(() => {})
      })

      credentials[role] = { username: prefix, password }
    }
  } catch (error) {
    for (const fn of cleanupStack.reverse()) {
      await fn()
    }
    throw error
  }

  return {
    credentials,
    cleanup: async () => {
      for (const fn of cleanupStack.reverse()) {
        await fn()
      }
    },
  }
}
