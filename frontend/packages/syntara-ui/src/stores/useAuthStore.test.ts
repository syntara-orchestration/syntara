import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { queryClient } from '../queryClient'

import {
  useAuthStore,
  isTokenExpired,
  EXPIRY_BUFFER_MS,
  AUTH_LOGIN_URL,
  AUTH_REFRESH_URL,
  AUTH_LOGOUT_URL,
  AUTH_CSRF_TOKEN_URL,
  clearScheduledRefresh,
} from './useAuthStore'

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function createTokenResponse(overrides?: Partial<{ access_token: string; token_type: string; expires_in: number }>) {
  return {
    access_token: 'test-access-token',
    token_type: 'Bearer',
    expires_in: 900,
    ...overrides,
  }
}

function mockFetchSuccess(data: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  })
}

function mockFetchError(detail: string, status = 401) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    text: () => Promise.resolve(JSON.stringify({ detail })),
  })
}

function mockLoginSuccess(tokenOverrides?: Partial<{ access_token: string; expires_in: number }>) {
  mockFetchSuccess(createTokenResponse(tokenOverrides))
  mockFetchSuccess({ csrf_token: 'test-csrf-token' })
}

describe('useAuthStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    useAuthStore.getState().reset()
    // Ensure no cached permission/data state leaks between tests
    queryClient.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('isTokenExpired', () => {
    it('returns true when expiresAt is null', () => {
      expect(isTokenExpired(null)).toBe(true)
    })

    it('returns true when token is expired', () => {
      const pastTime = Date.now() - 1000
      expect(isTokenExpired(pastTime)).toBe(true)
    })

    it('returns true when token is within the buffer window', () => {
      const almostExpired = Date.now() + EXPIRY_BUFFER_MS - 1000
      expect(isTokenExpired(almostExpired)).toBe(true)
    })

    it('returns false when token is still valid', () => {
      const futureTime = Date.now() + EXPIRY_BUFFER_MS + 60_000
      expect(isTokenExpired(futureTime)).toBe(false)
    })
  })

  describe('initial state', () => {
    it('starts unauthenticated', () => {
      const state = useAuthStore.getState()
      expect(state.accessToken).toBeNull()
      expect(state.expiresAt).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.isRefreshing).toBe(false)
      expect(state.error).toBeNull()
      expect(state.csrfToken).toBeNull()
    })
  })

  describe('login', () => {
    it('stores token and CSRF token on successful login', async () => {
      mockLoginSuccess()

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('test-access-token')
      expect(state.csrfToken).toBe('test-csrf-token')
      expect(state.isAuthenticated).toBe(true)
      expect(state.isRefreshing).toBe(false)
      expect(state.error).toBeNull()
      expect(state.expiresAt).toBeGreaterThan(Date.now())
    })

    it('posts to the login endpoint with credentials included', async () => {
      mockLoginSuccess()

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      expect(mockFetch).toHaveBeenCalledWith(AUTH_LOGIN_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Orchestrator-Client': 'ui' },
        credentials: 'include',
        body: JSON.stringify({ username: 'admin', password: 'admin' }),
      })
    })

    it('fetches CSRF token after successful login', async () => {
      mockLoginSuccess()

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(mockFetch.mock.calls[1][0]).toBe(AUTH_CSRF_TOKEN_URL)
      expect(mockFetch.mock.calls[1][1]).toEqual(
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          headers: { 'X-Orchestrator-Client': 'ui' },
        })
      )
    })

    it('sets error on login failure', async () => {
      mockFetchError('Invalid credentials', 401)

      await expect(useAuthStore.getState().login({ username: 'admin', password: 'wrong' })).rejects.toThrow(
        'Invalid credentials'
      )

      const state = useAuthStore.getState()
      expect(state.accessToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe('Invalid credentials')
      expect(state.csrfToken).toBeNull()
    })

    it('preserves logoutCount on login failure to prevent form remount', async () => {
      useAuthStore.setState({ logoutCount: 1, accessToken: null })
      mockFetchError('Invalid credentials', 401)

      await expect(useAuthStore.getState().login({ username: 'admin', password: 'wrong' })).rejects.toThrow(
        'Invalid credentials'
      )

      expect(useAuthStore.getState().logoutCount).toBe(1)
    })

    it('succeeds and remains authenticated when CSRF endpoint returns 404 (JWT-only backend)', async () => {
      mockFetchSuccess(createTokenResponse())
      mockFetchError('Not found', 404)

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.accessToken).toBe('test-access-token')
      expect(state.csrfToken).toBeNull()
      expect(state.error).toBeNull()
    })

    it('clears auth state when CSRF endpoint returns 403 (potential misconfiguration)', async () => {
      mockFetchSuccess(createTokenResponse())
      mockFetchError('CSRF cookie missing', 403)

      await expect(useAuthStore.getState().login({ username: 'admin', password: 'admin' })).rejects.toThrow(
        'CSRF cookie missing'
      )

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.accessToken).toBeNull()
      expect(state.csrfToken).toBeNull()
    })

    it('computes expiresAt from expires_in', async () => {
      const now = Date.now()
      vi.spyOn(Date, 'now').mockReturnValue(now)

      mockLoginSuccess({ expires_in: 600 })

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      const state = useAuthStore.getState()
      expect(state.expiresAt).toBe(now + 600 * 1000)
    })
  })

  describe('refresh', () => {
    it('updates token on successful refresh', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetchSuccess(createTokenResponse({ access_token: 'refreshed-token' }))

      await useAuthStore.getState().refresh()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('refreshed-token')
      expect(state.isAuthenticated).toBe(true)
    })

    it('sends X-CSRF-Token header on refresh when token is available', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetchSuccess(createTokenResponse({ access_token: 'refreshed' }))
      await useAuthStore.getState().refresh()

      expect(mockFetch).toHaveBeenCalledWith(
        AUTH_REFRESH_URL,
        expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- expect.objectContaining returns any
          headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf-token' }),
        })
      )
    })

    it('fetches CSRF token before refresh when csrfToken is null (OIDC bootstrap)', async () => {
      mockFetchSuccess({ csrf_token: 'bootstrap-csrf' })
      mockFetchSuccess(createTokenResponse({ access_token: 'bootstrapped' }))

      await useAuthStore.getState().refresh()

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(mockFetch.mock.calls[0][0]).toBe(AUTH_CSRF_TOKEN_URL)
      expect(mockFetch.mock.calls[1][0]).toBe(AUTH_REFRESH_URL)
      expect(useAuthStore.getState().accessToken).toBe('bootstrapped')
      expect(useAuthStore.getState().csrfToken).toBe('bootstrap-csrf')
    })

    it('proceeds without CSRF token when CSRF fetch fails (no cookie)', async () => {
      mockFetchError('CSRF cookie missing', 403)
      mockFetchSuccess(createTokenResponse({ access_token: 'no-csrf-refresh' }))

      await useAuthStore.getState().refresh()

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(useAuthStore.getState().accessToken).toBe('no-csrf-refresh')
    })

    it('posts to the refresh endpoint', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetchSuccess(createTokenResponse())

      await useAuthStore.getState().refresh()

      expect(mockFetch).toHaveBeenCalledWith(
        AUTH_REFRESH_URL,
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
        })
      )
    })

    it('clears auth state on refresh failure', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      expect(useAuthStore.getState().isAuthenticated).toBe(true)

      mockFetchError('Token expired', 401)

      await expect(useAuthStore.getState().refresh()).rejects.toThrow('Token expired')

      const state = useAuthStore.getState()
      expect(state.accessToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe('Token expired')
    })

    it('deduplicates concurrent refresh calls', async () => {
      mockFetchSuccess({ csrf_token: 'dedup-csrf' })
      mockFetchSuccess(createTokenResponse({ access_token: 'deduped-token' }))

      const p1 = useAuthStore.getState().refresh()
      const p2 = useAuthStore.getState().refresh()
      const p3 = useAuthStore.getState().refresh()

      await Promise.all([p1, p2, p3])

      // 1 CSRF fetch + 1 refresh = 2 total
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(useAuthStore.getState().accessToken).toBe('deduped-token')
    })

    it('clears isRefreshing when a refresh completes after logout (stale epoch)', async () => {
      const releaseBox: { fn?: (value: void | PromiseLike<void>) => void } = {}
      const refreshGate = new Promise<void>((resolve) => {
        releaseBox.fn = resolve
      })

      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockImplementationOnce(() =>
        refreshGate.then(() => ({
          ok: true,
          status: 200,
          json: () => Promise.resolve(createTokenResponse({ access_token: 'stale-refresh-token' })),
          text: () => Promise.resolve(JSON.stringify(createTokenResponse({ access_token: 'stale-refresh-token' }))),
        }))
      )

      const refreshDone = useAuthStore.getState().refresh()
      expect(useAuthStore.getState().isRefreshing).toBe(true)

      mockFetch.mockResolvedValueOnce({ ok: true, status: 200 })
      await useAuthStore.getState().logout()

      releaseBox.fn?.()
      await refreshDone

      expect(useAuthStore.getState().isRefreshing).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(useAuthStore.getState().accessToken).toBeNull()
    })

    it('skips CSRF fetch when refreshEpoch > 0 (active session refresh after previous logout)', async () => {
      useAuthStore.setState({ logoutCount: 1, accessToken: 'still-valid', csrfToken: null })
      mockFetchSuccess(createTokenResponse({ access_token: 'refreshed-token' }))

      await useAuthStore.getState().refresh()

      const csrfCalls = mockFetch.mock.calls.filter((call) => String(call[0]).includes('csrf_token'))
      expect(csrfCalls).toHaveLength(0)
      expect(useAuthStore.getState().accessToken).toBe('refreshed-token')
    })
  })

  describe('logout', () => {
    it('clears auth state after logout', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      expect(useAuthStore.getState().isAuthenticated).toBe(true)

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Successfully logged out' }),
      })

      await useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.expiresAt).toBeNull()
      expect(state.csrfToken).toBeNull()
    })

    it('sends X-CSRF-Token header on logout', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Successfully logged out' }),
      })

      await useAuthStore.getState().logout()

      const logoutCall = mockFetch.mock.calls[0]
      const logoutInit = logoutCall[1] as RequestInit
      const headers = logoutInit.headers as Record<string, string>
      expect(headers['X-CSRF-Token']).toBe('test-csrf-token')
      expect(headers['X-Orchestrator-Client']).toBe('ui')
    })

    it('posts to the logout endpoint with bearer token', async () => {
      mockLoginSuccess({ access_token: 'my-token' })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Successfully logged out' }),
      })
      await useAuthStore.getState().logout()

      const calledUrl = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0] as string
      expect(calledUrl).toContain(AUTH_LOGOUT_URL)
      expect(calledUrl).toContain('post_logout_redirect_uri')
    })

    it('clears local state when logout request fails (network), then rejects', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockRejectedValueOnce(new Error('Network error'))
      await expect(useAuthStore.getState().logout()).rejects.toThrow('Network error')

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(useAuthStore.getState().accessToken).toBeNull()
      expect(useAuthStore.getState().logoutCount).toBe(1)
      expect(useAuthStore.getState().csrfToken).toBeNull()
    })

    it('clears local state when logout returns non-OK, then rejects', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        text: () => Promise.resolve('Service unavailable'),
      })

      await expect(useAuthStore.getState().logout()).rejects.toThrow()

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(useAuthStore.getState().accessToken).toBeNull()
    })

    it('navigates to redirect_url when backend returns one (RP-initiated logout)', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      expect(useAuthStore.getState().isAuthenticated).toBe(true)

      // window.location's properties are getters on the prototype, not own properties, so
      // `...window.location` copies nothing. Set origin/href explicitly instead.
      const locationHrefSpy = vi.spyOn(window, 'location', 'get').mockReturnValue({
        origin: window.location.origin,
        href: window.location.href,
      } as Location)
      const hrefSetter = vi.fn()
      Object.defineProperty(window.location, 'href', { set: hrefSetter, configurable: true })

      const idpLogoutUrl = 'https://idp.example.com/logout?post_logout_redirect_uri=http%3A%2F%2Flocalhost%2F'
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Successfully logged out', redirect_url: idpLogoutUrl }),
      })

      await useAuthStore.getState().logout()

      // Should navigate to IdP logout endpoint
      expect(hrefSetter).toHaveBeenCalledWith(idpLogoutUrl)

      // Should clear local auth state
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.accessToken).toBeNull()
      expect(state.logoutCount).toBe(1)

      locationHrefSpy.mockRestore()
    })

    it('does not navigate when backend returns no redirect_url', async () => {
      mockLoginSuccess({ access_token: 'my-token' })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Successfully logged out' }),
      })
      await useAuthStore.getState().logout()

      // Should use fetch with post_logout_redirect_uri
      const calledUrl = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0] as string
      expect(calledUrl).toContain(AUTH_LOGOUT_URL)
      expect(calledUrl).toContain('post_logout_redirect_uri')

      // Should clear local auth state
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('ensureValidToken', () => {
    it('does nothing when token is still valid', async () => {
      mockLoginSuccess({ expires_in: 3600 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      await useAuthStore.getState().ensureValidToken()

      // No additional fetch calls
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('refreshes when token is expired', async () => {
      // Set up an expired token
      const now = Date.now()
      vi.spyOn(Date, 'now').mockReturnValue(now)

      mockLoginSuccess({ expires_in: 1 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      // Fast-forward past expiry
      vi.spyOn(Date, 'now').mockReturnValue(now + EXPIRY_BUFFER_MS + 2000)

      mockFetchSuccess(createTokenResponse({ access_token: 'refreshed-token' }))

      await useAuthStore.getState().ensureValidToken()

      expect(useAuthStore.getState().accessToken).toBe('refreshed-token')
    })

    it('refreshes when not authenticated', async () => {
      mockFetchSuccess({ csrf_token: 'bootstrap-csrf' })
      mockFetchSuccess(createTokenResponse({ access_token: 'new-token' }))

      await useAuthStore.getState().ensureValidToken()

      expect(useAuthStore.getState().accessToken).toBe('new-token')
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })
  })

  describe('clearAuth', () => {
    it('resets all auth state including CSRF token without calling logout endpoint', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      expect(useAuthStore.getState().csrfToken).toBe('test-csrf-token')
      mockFetch.mockClear()

      useAuthStore.getState().clearAuth()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBeNull()
      expect(state.csrfToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(mockFetch).not.toHaveBeenCalled()
    })
  })

  describe('background refresh timer', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      clearScheduledRefresh()
      vi.useRealTimers()
    })

    it('schedules a background refresh after login', async () => {
      mockLoginSuccess({ expires_in: 300 })

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      mockFetch.mockClear()

      mockFetchSuccess(createTokenResponse({ access_token: 'timer-refreshed' }))

      // expires_in=300s, timer fires at 300s - 60s = 240s
      await vi.advanceTimersByTimeAsync(240_000)

      expect(mockFetch).toHaveBeenCalledWith(AUTH_REFRESH_URL, expect.objectContaining({ method: 'POST' }))
      expect(useAuthStore.getState().accessToken).toBe('timer-refreshed')
    })

    it('schedules a background refresh after token refresh', async () => {
      mockLoginSuccess({ expires_in: 300 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      // Manual refresh
      mockFetchSuccess(createTokenResponse({ access_token: 'first-refresh', expires_in: 300 }))
      await useAuthStore.getState().refresh()
      mockFetch.mockClear()

      // Timer should be rescheduled after the manual refresh
      mockFetchSuccess(createTokenResponse({ access_token: 'timer-refresh-2' }))
      await vi.advanceTimersByTimeAsync(240_000)

      expect(useAuthStore.getState().accessToken).toBe('timer-refresh-2')
    })

    it('uses minimum 10 second delay for short-lived tokens', async () => {
      mockLoginSuccess({ expires_in: 5 })

      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetchSuccess(createTokenResponse({ access_token: 'short-token-refresh' }))

      // Should not fire before 10s
      await vi.advanceTimersByTimeAsync(9_000)
      expect(mockFetch).not.toHaveBeenCalled()

      // Should fire at 10s (minimum delay)
      await vi.advanceTimersByTimeAsync(1_000)

      expect(mockFetch).toHaveBeenCalled()
    })

    it('clears timer on logout', async () => {
      mockLoginSuccess({ expires_in: 300 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'logged out' }),
      })
      await useAuthStore.getState().logout()
      mockFetch.mockClear()

      // Timer should not fire after logout
      vi.advanceTimersByTime(300_000)
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('clears timer on clearAuth', async () => {
      mockLoginSuccess({ expires_in: 300 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      useAuthStore.getState().clearAuth()

      // Timer should not fire after clearAuth
      vi.advanceTimersByTime(300_000)
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('clears timer on reset', async () => {
      mockLoginSuccess({ expires_in: 300 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      useAuthStore.getState().reset()

      // Timer should not fire after reset
      vi.advanceTimersByTime(300_000)
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('does not throw when timer-triggered refresh fails', async () => {
      mockLoginSuccess({ expires_in: 300 })
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })
      mockFetch.mockClear()

      // Refresh will fail — scheduleRefresh logs the error but doesn't throw
      mockFetchError('Token expired', 401)

      await vi.advanceTimersByTimeAsync(240_000)

      expect(mockFetch).toHaveBeenCalled()
    })
  })

  describe('query cache invalidation', () => {
    const SEED_QUERY_KEY = ['authz', 'can_i', { action: 'read', resource_type: 'workflow' }]
    const SEED_DATA = { data: { allowed: true } }

    function seedCache() {
      queryClient.setQueryData(SEED_QUERY_KEY, SEED_DATA)
      expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
    }

    it('logout() clears the query cache', async () => {
      seedCache()
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      await useAuthStore.getState().logout()

      expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    })

    it('clearAuth() clears the query cache', () => {
      seedCache()

      useAuthStore.getState().clearAuth()

      expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    })

    it('refresh() failure clears the query cache', async () => {
      seedCache()
      // Simulate CSRF fetch succeeding but refresh failing
      mockFetchSuccess({ csrf_token: 'test-csrf' })
      mockFetchError('Token expired', 401)

      await expect(useAuthStore.getState().refresh()).rejects.toThrow('Token expired')

      expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    })

    it('login() failure does NOT clear the query cache', async () => {
      // Login failure should not clear the cache — the user has no prior session
      // to leak, and clearing here would evict unrelated cached data unnecessarily
      seedCache()
      mockFetchError('Invalid credentials', 401)

      await expect(useAuthStore.getState().login({ username: 'admin', password: 'wrong' })).rejects.toThrow(
        'Invalid credentials'
      )

      expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
    })
  })

  describe('refresh skip guards', () => {
    it('skips refresh when logoutCount > 0 and no accessToken', async () => {
      // Simulate post-logout state: logoutCount incremented, accessToken cleared
      useAuthStore.setState({ logoutCount: 1, accessToken: null })

      await useAuthStore.getState().refresh()

      // No fetch calls should have been made
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('skips refresh when sessionStorage has explicit logout key', async () => {
      sessionStorage.setItem('ao_explicit_logout', '1')

      await useAuthStore.getState().refresh()

      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('does NOT skip refresh when logoutCount > 0 but accessToken exists', async () => {
      useAuthStore.setState({ logoutCount: 1, accessToken: 'still-valid' })
      mockFetchSuccess({ csrf_token: 'csrf' })
      mockFetchSuccess(createTokenResponse())

      await useAuthStore.getState().refresh()

      expect(mockFetch).toHaveBeenCalled()
    })
  })

  describe('logout auth_error handling', () => {
    it('redirects to login with auth_error param when backend returns auth_error', async () => {
      mockLoginSuccess()
      await useAuthStore.getState().login({ username: 'admin', password: 'admin' })

      const hrefSetter = vi.fn()
      const locationSpy = vi.spyOn(window, 'location', 'get').mockReturnValue({
        ...window.location,
        origin: 'http://localhost',
        href: 'http://localhost/',
      } as Location)
      Object.defineProperty(window.location, 'href', { set: hrefSetter, configurable: true })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ detail: 'Logged out', auth_error: 'end_session_failed' }),
      })

      await useAuthStore.getState().logout()

      expect(hrefSetter).toHaveBeenCalledWith(expect.stringContaining('auth_error=end_session_failed'))

      locationSpy.mockRestore()
    })
  })

  describe('JWT parsing', () => {
    function fakeJwt(payload: Record<string, unknown>): string {
      const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
      const body = btoa(JSON.stringify(payload))
      return `${header}.${body}.fake-signature`
    }

    it('parses username and userId from a JWT access token', async () => {
      const token = fakeJwt({ preferred_username: 'alice', sub: 'user-42' })
      mockFetchSuccess(createTokenResponse({ access_token: token }))
      mockFetchSuccess({ csrf_token: 'csrf' })

      await useAuthStore.getState().login({ username: 'alice', password: 'pass' })

      expect(useAuthStore.getState().username).toBe('alice')
      expect(useAuthStore.getState().userId).toBe('user-42')
    })

    it('handles token without preferred_username gracefully', async () => {
      const token = fakeJwt({ sub: 'user-99' })
      mockFetchSuccess(createTokenResponse({ access_token: token }))
      mockFetchSuccess({ csrf_token: 'csrf' })

      await useAuthStore.getState().login({ username: 'admin', password: 'pass' })

      expect(useAuthStore.getState().username).toBeNull()
      expect(useAuthStore.getState().userId).toBe('user-99')
    })

    it('returns null for malformed JWT payload', async () => {
      const malformed = 'header.!!!invalid-base64!!!.sig'
      mockFetchSuccess(createTokenResponse({ access_token: malformed }))
      mockFetchSuccess({ csrf_token: 'csrf' })

      await useAuthStore.getState().login({ username: 'admin', password: 'pass' })

      expect(useAuthStore.getState().username).toBeNull()
      expect(useAuthStore.getState().userId).toBeNull()
    })
  })
})
