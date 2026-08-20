/**
 * Auth Store
 *
 * Zustand store managing JWT access token lifecycle.
 * - Access token stored in memory only (never localStorage/sessionStorage)
 * - Refresh via HttpOnly cookie `ao_refresh_token` (managed by backend)
 */

import { create } from 'zustand'

import { EXPLICIT_LOGOUT_KEY } from '../components/session/sessionTimeoutConstants'
import { queryClient } from '../queryClient'
import { orchestratorUiClientHeaders } from '../utils/orchestratorClientHeader'

// ============================================================================
// Types
// ============================================================================

type LoginResponse = {
  access_token: string
  token_type: string
  expires_in: number
}

type AuthState = {
  accessToken: string | null
  expiresAt: number | null
  isAuthenticated: boolean
  isRefreshing: boolean
  error: string | null
  logoutCount: number
  username: string | null
  userId: string | null
  csrfToken: string | null
}

type LoginCredentials = {
  username: string
  password: string
}

type AuthActions = {
  login: (credentials: LoginCredentials) => Promise<void>
  refresh: () => Promise<void>
  logout: () => Promise<void>
  ensureValidToken: () => Promise<void>
  clearAuth: () => void
  reset: () => void
}

type AuthStore = AuthState & AuthActions

// ============================================================================
// Constants
// ============================================================================

const AUTH_LOGIN_URL = '/api/v1/auth/login'
const AUTH_REFRESH_URL = '/api/v1/auth/refresh'
const AUTH_LOGOUT_URL = '/api/v1/auth/logout'
const AUTH_CSRF_TOKEN_URL = '/api/v1/auth/csrf_token'

/** Refresh the token 30 seconds before it actually expires */
const EXPIRY_BUFFER_MS = 30_000

/** Background timer fires 60s before expiry — well ahead of EXPIRY_BUFFER_MS so the refresh completes in time */
const PROACTIVE_REFRESH_BUFFER_MS = 60_000

const INITIAL_STATE: AuthState = {
  accessToken: null,
  expiresAt: null,
  isAuthenticated: false,
  isRefreshing: false,
  error: null,
  logoutCount: 0,
  username: null,
  userId: null,
  csrfToken: null,
}

// ============================================================================
// AuthError — preserves RFC 9457 error code from backend responses
// ============================================================================

export class AuthError extends Error {
  readonly code: string

  constructor(message: string, code: string) {
    super(message)
    this.name = 'AuthError'
    this.code = code
  }
}

// ============================================================================
// Helpers
// ============================================================================

type LogoutResponse = {
  error: Error | null
  /** URL to redirect the browser to for RP-initiated IdP logout. */
  redirectUrl?: string
  /** User-facing error from the backend when IdP logout fails. */
  authError?: string
}

/**
 * Revoke the session server-side via POST to the logout endpoint.
 *
 * The backend always returns JSON. When RP-initiated logout is active and
 * the IdP's end_session_endpoint is resolvable, the response includes a
 * `redirect_url` that the caller should navigate to via
 * `window.location.href` so the browser sends first-party IdP cookies.
 */
function buildAuthHeaders(accessToken: string | null, csrfToken: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...orchestratorUiClientHeaders(),
  }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  return headers
}

async function revokeServerSession(accessToken: string | null, csrfToken: string | null): Promise<LogoutResponse> {
  try {
    const logoutUrl = new URL(AUTH_LOGOUT_URL, window.location.origin)
    logoutUrl.searchParams.set('post_logout_redirect_uri', `${window.location.origin}/`)

    // eslint-disable-next-line syntara/no-raw-http-calls -- auth: logout before token middleware teardown
    const response = await fetch(logoutUrl.toString(), {
      method: 'POST',
      headers: buildAuthHeaders(accessToken, csrfToken),
      credentials: 'include',
    })

    if (!response.ok) {
      const text = await response.text()
      let detail = `Sign out failed (${response.status})`
      try {
        const parsed: Record<string, unknown> = JSON.parse(text) as Record<string, unknown>
        const msg = parsed.detail ?? parsed.message
        if (typeof msg === 'string') detail = msg
      } catch {
        if (text) detail = text
      }
      return { error: new Error(detail) }
    }

    // Parse optional redirect_url and auth_error from the response body.
    let redirectUrl: string | undefined
    let authError: string | undefined
    try {
      const body: Record<string, unknown> = (await response.json()) as Record<string, unknown>
      if (typeof body.redirect_url === 'string') {
        redirectUrl = body.redirect_url
      }
      if (typeof body.auth_error === 'string') {
        authError = body.auth_error
      }
    } catch {
      // Empty or non-JSON body — no redirect needed.
    }

    return { error: null, redirectUrl, authError }
  } catch (err) {
    return { error: err instanceof Error ? err : new Error(String(err)) }
  }
}

function isTokenExpired(expiresAt: number | null): boolean {
  if (expiresAt === null) return true
  return Date.now() >= expiresAt - EXPIRY_BUFFER_MS
}

async function throwResponseError(response: Response): Promise<never> {
  const text = await response.text()
  let detail = text
  let code: string | undefined
  try {
    const parsed: Record<string, unknown> = JSON.parse(text) as Record<string, unknown>
    const msg = parsed.detail ?? parsed.message
    if (typeof msg === 'string') detail = msg
    if (typeof parsed.code === 'string') code = parsed.code
  } catch {
    // use raw text
  }
  throw code ? new AuthError(detail, code) : new Error(detail)
}

/**
 * Fetch the CSRF token.
 * Pass `true` to return `null` on 404 (JWT-only backends have no CSRF endpoint).
 * Any other non-2xx status always throws — a 403 or 500 indicates genuine misconfiguration.
 */
async function fetchCsrfToken(): Promise<string>
async function fetchCsrfToken(returnNullOn404: true): Promise<string | null>
async function fetchCsrfToken(returnNullOn404 = false): Promise<string | null> {
  // eslint-disable-next-line syntara/no-raw-http-calls -- auth: CSRF token fetch before client is initialized
  const response = await fetch(AUTH_CSRF_TOKEN_URL, {
    method: 'POST',
    headers: orchestratorUiClientHeaders(),
    credentials: 'include',
  })

  if (response.status === 404 && returnNullOn404) return null
  if (!response.ok) await throwResponseError(response)

  const body = (await response.json()) as { csrf_token: string }
  return body.csrf_token
}

async function postAuth(url: string, body?: object, extraHeaders?: Record<string, string>): Promise<LoginResponse> {
  // eslint-disable-next-line syntara/no-raw-http-calls -- auth: login/token exchange before client is initialized
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...orchestratorUiClientHeaders(), ...extraHeaders },
    credentials: 'include', // ensure HttpOnly cookies are sent
    ...(body ? { body: JSON.stringify(body) } : {}),
  })

  if (!response.ok) await throwResponseError(response)

  return (await response.json()) as LoginResponse
}

type JwtPayload = {
  preferred_username?: string
  sub?: string
}

function parseJwtPayload(token: string): JwtPayload | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    return JSON.parse(atob(padded)) as JwtPayload
  } catch {
    return null
  }
}

function parseUsernameFromJwt(token: string): string | null {
  const payload = parseJwtPayload(token)
  return payload?.preferred_username ?? null
}

function parseUserIdFromJwt(token: string): string | null {
  const payload = parseJwtPayload(token)
  return payload?.sub ?? null
}

function applyTokenResponse(
  set: (partial: Partial<AuthState>) => void,
  data: LoginResponse,
  refreshFn: () => Promise<void>
): void {
  sessionStorage.removeItem(EXPLICIT_LOGOUT_KEY)
  set({
    accessToken: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
    isAuthenticated: true,
    isRefreshing: false,
    error: null,
    username: parseUsernameFromJwt(data.access_token),
    userId: parseUserIdFromJwt(data.access_token),
  })
  scheduleRefresh(data.expires_in, refreshFn)
}

// ============================================================================
// Store
// ============================================================================

/** In-flight refresh promise used to deduplicate concurrent refresh calls */
let refreshPromise: Promise<void> | null = null

/** Background timer that proactively refreshes the token before it expires */
let refreshTimer: ReturnType<typeof setTimeout> | null = null

function scheduleRefresh(expiresInSeconds: number, refreshFn: () => Promise<void>): void {
  clearScheduledRefresh()
  const delay = Math.max(expiresInSeconds * 1000 - PROACTIVE_REFRESH_BUFFER_MS, 10_000)
  refreshTimer = setTimeout(() => {
    refreshFn().catch(() => {
      // eslint-disable-next-line no-console -- generic message only; detailed errors stay server-side
      console.error('Background token refresh failed')
    })
  }, delay)
}

function clearScheduledRefresh(): void {
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  ...INITIAL_STATE,

  login: async (credentials: LoginCredentials) => {
    set({ isRefreshing: true, error: null })
    try {
      const data = await postAuth(AUTH_LOGIN_URL, credentials)
      applyTokenResponse(set, data, () => get().refresh())
      // null = JWT-only backend (no CSRF endpoint), not "failed to fetch"
      const csrfToken = await fetchCsrfToken(true)
      set({ csrfToken })
    } catch (err) {
      set({
        ...INITIAL_STATE,
        logoutCount: get().logoutCount,
        error: err instanceof Error ? err.message : String(err),
      })
      throw err
    }
  },

  refresh: async () => {
    // Deduplicate: if a refresh is already in flight, wait for it
    if (refreshPromise) {
      await refreshPromise
      return
    }

    // After explicit logout (logoutCount > 0), the session cookie is revoked.
    // Skip the refresh entirely to avoid pointless 403/401 network errors in
    // the console. On OIDC re-auth the page reloads, resetting logoutCount to 0.
    const { logoutCount, accessToken } = get()
    if (logoutCount > 0 && !accessToken) {
      return
    }

    // On page refresh after explicit logout, Zustand resets (logoutCount === 0)
    // but sessionStorage retains the signal. Skip the bootstrap refresh to avoid
    // network 403s against the revoked session cookie.
    if (!accessToken && sessionStorage.getItem(EXPLICIT_LOGOUT_KEY)) {
      return
    }

    set({ isRefreshing: true, error: null })
    // `logout` increments `logoutCount` so we can drop stale refresh results after sign-out.
    const refreshEpoch = get().logoutCount

    // Holder avoids referencing `const currentRefresh` inside the IIFE before assignment (TS2454 / TDZ).
    const inFlightRefresh: { promise: Promise<void> | null } = { promise: null }
    const currentRefresh = (async () => {
      try {
        let { csrfToken } = get()
        if (!csrfToken) {
          // Only attempt CSRF fetch when a session likely exists:
          // - refreshEpoch === 0: first page load / OIDC bootstrap (cookie from IdP redirect)
          // After explicit logout (refreshEpoch > 0, no accessToken), the session
          // cookie is revoked so the CSRF endpoint will always 403.
          const shouldFetchCsrf = refreshEpoch === 0
          if (shouldFetchCsrf) {
            try {
              csrfToken = await fetchCsrfToken()
              set({ csrfToken })
            } catch {
              // OIDC bootstrap: the CSRF cookie may not exist yet on the first
              // page load after an IdP redirect, so this fetch can legitimately
              // 403. Refresh proceeds without the X-CSRF-Token header — the
              // server enforces CSRF validation and will reject the request if
              // the token is actually required, so security is not weakened.
            }
          }
        }
        const csrfHeaders: Record<string, string> = csrfToken ? { 'X-CSRF-Token': csrfToken } : {}
        const data = await postAuth(AUTH_REFRESH_URL, undefined, csrfHeaders)
        if (get().logoutCount !== refreshEpoch) {
          return
        }
        applyTokenResponse(set, data, () => get().refresh())
      } catch (err) {
        if (get().logoutCount !== refreshEpoch) {
          return
        }
        set({
          ...INITIAL_STATE,
          error: err instanceof Error ? err.message : String(err),
        })
        // Prevent stale permission/data cache from leaking to the next user session
        queryClient.clear()
        throw err
      } finally {
        if (refreshPromise === inFlightRefresh.promise) {
          refreshPromise = null
        }
        // Stale-invocation early returns (epoch mismatch) skip applyTokenResponse / INITIAL_STATE — still
        // clear the spinner or AppLogin stays on SynLoadingState forever after sign-out or parallel logout.
        set({ isRefreshing: false })
      }
    })()

    inFlightRefresh.promise = currentRefresh
    refreshPromise = currentRefresh
    await currentRefresh
  },

  logout: async () => {
    const { accessToken, csrfToken, logoutCount } = get()
    clearScheduledRefresh()
    // Drop any in-flight refresh waiters — otherwise AppLogin bootstrap can await this forever and
    // never leave the loading state. Stale refresh completions are ignored via `logoutCount` / epoch.
    refreshPromise = null

    // Clear local state BEFORE the async revocation so that any concurrent
    // refresh() call (e.g. from authMiddleware responding to a 401 on an
    // in-flight request) sees logoutCount > 0 and bails out immediately.
    // The captured accessToken/csrfToken locals are used for the revocation.
    sessionStorage.setItem(EXPLICIT_LOGOUT_KEY, '1')
    set({ ...INITIAL_STATE, logoutCount: logoutCount + 1 })
    // Prevent stale permission/data cache from leaking to the next user session
    queryClient.clear()

    const { error, redirectUrl, authError } = await revokeServerSession(accessToken, csrfToken)

    if (error) {
      throw error
    }

    // RP-initiated logout: the backend returned a redirect URL pointing to
    // the IdP's end_session_endpoint.  Navigate via window.location.href so
    // the browser sends first-party IdP cookies (HttpOnly included) and the
    // IdP session is terminated.
    if (redirectUrl) {
      window.location.href = redirectUrl
    } else if (authError) {
      // IdP logout failed (e.g. end_session_endpoint unresolvable) — pass the
      // error to the login page via URL param so it displays on mount.
      const loginUrl = new URL('/', window.location.origin)
      loginUrl.searchParams.set('auth_error', authError)
      window.location.href = loginUrl.toString()
    }
  },

  ensureValidToken: async () => {
    const { accessToken, expiresAt, isAuthenticated } = get()

    if (isAuthenticated && accessToken && !isTokenExpired(expiresAt)) {
      return // token is still valid
    }

    // Token missing or expired — attempt refresh
    await get().refresh()
  },

  clearAuth: () => {
    clearScheduledRefresh()
    set({ ...INITIAL_STATE })
    // Prevent stale permission/data cache from leaking to the next user session
    queryClient.clear()
  },

  reset: () => {
    clearScheduledRefresh()
    refreshPromise = null
    set({ ...INITIAL_STATE })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectIsAuthenticated = (state: AuthStore) => state.isAuthenticated
export const selectIsRefreshing = (state: AuthStore) => state.isRefreshing

// ============================================================================
// Exported for testing
// ============================================================================

export {
  isTokenExpired,
  AUTH_LOGIN_URL,
  AUTH_REFRESH_URL,
  AUTH_LOGOUT_URL,
  AUTH_CSRF_TOKEN_URL,
  EXPIRY_BUFFER_MS,
  clearScheduledRefresh,
}
export type { LoginCredentials, LoginResponse, AuthState, AuthStore }
