/**
 * Regression tests for the stale-token retry in `apiRequest`.
 *
 * The whole suite authenticates as the same `admin` account, and `POST
 * /auth/logout` increments that account's `token_version`, invalidating every
 * access token it holds. A spec that logs out therefore ages the token another
 * worker's `beforeAll` fetched once and is still reusing across dozens of seed
 * calls — the backend answers `401 {"code":"TOKEN_STALE","retryable":true}` and,
 * before this retry existed, the seeding hook died mid-loop.
 *
 * The race between workers is not reproducible on demand, so these tests assert
 * the invariant the fix establishes — a stale token is refreshed and the request
 * replayed — against a stub backend that revokes tokens when told to.
 */
import { test, expect, type Page } from './fixtures'
import { apiRequest, apiUrl } from './utils/api'

/** The verbatim body the backend returned in CI (run 34382665277). */
const STALE_TOKEN_BODY = {
  type: 'https://api.example.com/errors/unauthorized',
  title: 'Unauthorized',
  detail: 'Token is outdated, please refresh',
  code: 'TOKEN_STALE',
  retryable: true,
  instance: 'https://localhost/api/v1/users',
}

/** A 401 that is *not* a stale token — wrong credentials, and not retryable. */
const FORBIDDEN_BODY = {
  type: 'https://api.example.com/errors/unauthorized',
  title: 'Unauthorized',
  detail: 'Not authenticated',
  code: 'NOT_AUTHENTICATED',
  retryable: false,
}

function stubResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  const text = JSON.stringify(body)
  return {
    status: () => status,
    ok: () => status >= 200 && status < 300,
    // `apiRequest` reads `X-Auth-Failure-Type` before falling back to the body,
    // so the stub has to answer `headers()` — without it every 401 path throws a
    // TypeError and the test errors rather than failing.
    headers: () => headers,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text) as unknown),
  }
}

/**
 * Minimal stand-in for the backend's token-version check.
 *
 * Tokens carry the version they were issued at; `revokeTokens()` is the logout
 * another worker performs, and any request presenting an older token afterwards
 * gets the same 401 the real middleware returns.
 */
function createStubBackend({ emitFailureHeader = false }: { emitFailureHeader?: boolean } = {}) {
  const seeded: unknown[] = []
  let tokenVersion = 1
  let logins = 0

  // The metrics middleware normally strips `X-Auth-Failure-Type` before the
  // response reaches a client, which is why the body `code` is the path that
  // actually fires in CI. Both are worth pinning.
  const staleHeaders: Record<string, string> = emitFailureHeader ? { 'x-auth-failure-type': 'stale_token' } : {}

  const respondTo = (url: string, headers: Record<string, string> | undefined, data: unknown) => {
    if (url === apiUrl('/auth/login')) {
      logins += 1
      return stubResponse(200, { access_token: `admin-token-v${tokenVersion}` })
    }

    const token = headers?.['Authorization']?.replace('Bearer ', '') ?? null
    if (token === null) return stubResponse(401, FORBIDDEN_BODY)
    if (token !== `admin-token-v${tokenVersion}`) return stubResponse(401, STALE_TOKEN_BODY, staleHeaders)

    seeded.push(data)
    return stubResponse(201, { id: `user-${seeded.length}`, username: 'seeded' })
  }

  const request = {
    get: (url: string, options?: { headers?: Record<string, string> }) =>
      Promise.resolve(respondTo(url, options?.headers, undefined)),
    post: (url: string, options?: { headers?: Record<string, string>; data?: unknown }) =>
      Promise.resolve(respondTo(url, options?.headers, options?.data)),
    patch: (url: string, options?: { headers?: Record<string, string>; data?: unknown }) =>
      Promise.resolve(respondTo(url, options?.headers, options?.data)),
    delete: (url: string, options?: { headers?: Record<string, string> }) =>
      Promise.resolve(respondTo(url, options?.headers, undefined)),
  }

  return {
    page: { request, waitForTimeout: () => Promise.resolve() } as unknown as Page,
    issueToken: () => `admin-token-v${tokenVersion}`,
    /** Another worker logged the shared admin account out. */
    revokeTokens: () => {
      tokenVersion += 1
    },
    get logins() {
      return logins
    },
    get seeded() {
      return seeded
    },
  }
}

test.describe('apiRequest stale-token retry', () => {
  // Pure helper — no page, no login, no backend.
  test('re-authenticates and replays when a cached token has gone stale', async () => {
    const backend = createStubBackend()
    const cachedToken = backend.issueToken()

    backend.revokeTokens()

    const resp = await apiRequest(backend.page, 'post', '/users', {
      token: cachedToken,
      data: { username: 'e2e-pag-user-15' },
    })

    expect(resp.status()).toBe(201)
    expect(backend.seeded).toHaveLength(1)
    // Exactly one extra login: the retry, not a login per attempt.
    expect(backend.logins).toBe(1)
  })

  test('recognises the stale token from the X-Auth-Failure-Type header alone', async () => {
    const backend = createStubBackend({ emitFailureHeader: true })
    const cachedToken = backend.issueToken()

    backend.revokeTokens()

    const resp = await apiRequest(backend.page, 'post', '/users', {
      token: cachedToken,
      data: { username: 'e2e-pag-user-16' },
    })

    expect(resp.status()).toBe(201)
    expect(backend.logins).toBe(1)
  })

  test('does not re-authenticate when the request succeeds', async () => {
    const backend = createStubBackend()

    const resp = await apiRequest(backend.page, 'post', '/users', {
      token: backend.issueToken(),
      data: { username: 'e2e-pag-user-1' },
    })

    expect(resp.status()).toBe(201)
    expect(backend.logins).toBe(0)
  })

  test('surfaces a 401 that is not a stale token instead of retrying it', async () => {
    const backend = createStubBackend()

    const resp = await apiRequest(backend.page, 'get', '/users', { token: '' })

    expect(resp.status()).toBe(401)
    // A genuine auth failure must stay visible; retrying it would only hide it.
    expect(backend.logins).toBe(0)
  })
})
