/**
 * Core API utilities for E2E test setup/teardown.
 *
 * Provides authentication, request helpers, and project management
 * that all other domain-specific API modules depend on.
 */
import type { APIResponse } from '@playwright/test'

import { appBaseUrl, type Page } from '../fixtures'

/** Get the API base URL (proxied through the UI server) */
export function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, appBaseUrl).toString()
}

const AUTH_ATTEMPTS = 3
const AUTH_RETRY_DELAY = 500
const STALE_TOKEN_FAILURE_HEADER = 'stale_token'

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

async function isStaleTokenResponse(response: APIResponse): Promise<boolean> {
  if (response.status() !== 401) return false

  const failureType = response.headers()['x-auth-failure-type']
  if (failureType === STALE_TOKEN_FAILURE_HEADER) return true

  // Metrics middleware strips X-Auth-Failure-Type before the response reaches clients.
  try {
    const body = (await response.json()) as { code?: string }
    return body.code === 'TOKEN_STALE'
  } catch {
    return false
  }
}

async function sendApiRequest(
  app: Page,
  method: 'get' | 'post' | 'patch' | 'delete',
  path: string,
  token: string | null,
  data?: unknown
): Promise<APIResponse> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = apiUrl(path)
  if (method === 'get') return app.request.get(url, { headers })
  if (method === 'post') return app.request.post(url, { headers, data })
  if (method === 'patch') return app.request.patch(url, { headers, data })
  return app.request.delete(url, { headers })
}

/**
 * Make an authenticated API request.
 *
 * `POST /auth/logout` increments the user's `token_version`, which invalidates
 * every access token that user holds — not just the session that logged out.
 * The whole suite authenticates as the same `admin` account, and seed helpers
 * fetch one token in `beforeAll` then reuse it across dozens of sequential
 * calls, so one worker running a spec that logs out ages every other worker's
 * cached token and leaves the spec dead in a hook with
 * `401 {"code":"TOKEN_STALE",…}`.
 *
 * Re-authenticate once and replay — which is exactly what the backend's
 * `retryable: true` asks the client to do. A refresh that hands back the same
 * token cannot succeed on replay, so return the original rejection rather than
 * spending a second request proving it.
 */
export async function apiRequest(
  app: Page,
  method: 'get' | 'post' | 'patch' | 'delete',
  path: string,
  options?: { data?: unknown; token?: string }
) {
  const token = options?.token ?? (await getAuthToken(app))
  const response = await sendApiRequest(app, method, path, token, options?.data)

  if (!(await isStaleTokenResponse(response))) return response

  const refreshed = await getAuthToken(app)
  if (!refreshed || refreshed === token) return response

  return sendApiRequest(app, method, path, refreshed, options?.data)
}

/**
 * Ensure a project exists and return its ID.
 * Lists projects first; creates one if missing. Returns null if API is unavailable.
 */
export async function ensureProject(app: Page, name = 'default'): Promise<{ id: string; name: string } | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const listResp = await apiRequest(app, 'get', '/projects?limit=100', { token })
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
 * Look up a project ID by exact name. Returns null when it cannot be found.
 *
 * Mirrors `findWorkflowIdByName`, but lists and matches client-side because
 * `/projects` is not known to support `name[contains]` — `ensureProject` above
 * already takes the same `?limit=100` approach.
 */
export async function findProjectIdByName(app: Page, name: string): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null
    const resp = await apiRequest(app, 'get', '/projects?limit=100', { token })
    if (!resp.ok()) return null
    const body = (await resp.json()) as { resources?: Array<{ id: string; name: string }> }
    return body.resources?.find((project) => project.name === name)?.id ?? null
  } catch {
    return null
  }
}

/** Create a project via the API. Returns the project ID. */
export async function createProjectViaApi(app: Page, name: string, description?: string): Promise<{ id: string }> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('createProjectViaApi: could not obtain auth token')
  const resp = await apiRequest(app, 'post', '/projects', {
    token,
    data: { name, description: description ?? `E2E test project: ${name}` },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /projects returned ${resp.status()}: ${body}`)
  }
  return (await resp.json()) as { id: string }
}

/** Delete a project by ID via the API (best-effort cleanup). */
export async function deleteProjectViaApi(app: Page, projectId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/projects/${projectId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}
