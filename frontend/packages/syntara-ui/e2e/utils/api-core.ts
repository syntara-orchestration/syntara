/**
 * Core API utilities for E2E test setup/teardown.
 *
 * Provides authentication, request helpers, and project management
 * that all other domain-specific API modules depend on.
 */
import { appBaseUrl, type Page } from '../fixtures'

/** Get the API base URL (proxied through the UI server) */
export function apiUrl(path: string): string {
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
