import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { authMiddleware, interfaceTagMiddleware } from './client'
import { useAuthStore } from './stores/useAuthStore'

// Must import after vi.mock so the middleware picks up the mocked store

vi.mock('./stores/useAuthStore', () => ({
  useAuthStore: {
    getState: vi.fn(),
  },
}))

const mockGetState = useAuthStore.getState as ReturnType<typeof vi.fn>

describe('interfaceTagMiddleware', () => {
  it('sets X-Orchestrator-Client header to ui on every request', async () => {
    const request = new Request('https://example.com/api/v1/workflows')
    const result = await interfaceTagMiddleware.onRequest!({ request } as Parameters<
      NonNullable<typeof interfaceTagMiddleware.onRequest>
    >[0])

    expect((result as Request).headers.get('X-Orchestrator-Client')).toBe('ui')
  })

  it('preserves existing request headers', async () => {
    const request = new Request('https://example.com/api/v1/workflows', {
      headers: { 'Content-Type': 'application/json' },
    })
    const result = await interfaceTagMiddleware.onRequest!({ request } as Parameters<
      NonNullable<typeof interfaceTagMiddleware.onRequest>
    >[0])

    expect((result as Request).headers.get('Content-Type')).toBe('application/json')
    expect((result as Request).headers.get('X-Orchestrator-Client')).toBe('ui')
  })
})

describe('authMiddleware', () => {
  const mockEnsureValidToken = vi.fn()
  const mockRefresh = vi.fn()
  const mockClearAuth = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('onRequest', () => {
    it('sets Authorization header when token is available', async () => {
      mockGetState
        .mockReturnValueOnce({
          ensureValidToken: mockEnsureValidToken,
        })
        .mockReturnValueOnce({
          accessToken: 'test-token',
        })
      mockEnsureValidToken.mockResolvedValueOnce(undefined)

      const request = new Request('https://example.com/api')
      const result = await authMiddleware.onRequest!({ request } as Parameters<
        NonNullable<typeof authMiddleware.onRequest>
      >[0])

      expect(mockEnsureValidToken).toHaveBeenCalled()
      expect((result as Request).headers.get('Authorization')).toBe('Bearer test-token')
    })

    it('does not set Authorization header when no token', async () => {
      mockGetState
        .mockReturnValueOnce({
          ensureValidToken: mockEnsureValidToken,
        })
        .mockReturnValueOnce({
          accessToken: null,
        })
      mockEnsureValidToken.mockResolvedValueOnce(undefined)

      const request = new Request('https://example.com/api')
      const result = await authMiddleware.onRequest!({ request } as Parameters<
        NonNullable<typeof authMiddleware.onRequest>
      >[0])

      expect((result as Request).headers.has('Authorization')).toBe(false)
    })

    it('returns request without auth when ensureValidToken fails', async () => {
      mockGetState.mockReturnValueOnce({
        ensureValidToken: mockEnsureValidToken,
      })
      mockEnsureValidToken.mockRejectedValueOnce(new Error('Token expired'))

      const request = new Request('https://example.com/api')
      const result = await authMiddleware.onRequest!({ request } as Parameters<
        NonNullable<typeof authMiddleware.onRequest>
      >[0])

      expect(result).toBe(request)
      expect((result as Request).headers.has('Authorization')).toBe(false)
    })
  })

  describe('onResponse', () => {
    it('returns response as-is for non-401 status', async () => {
      const request = new Request('https://example.com/api')
      const response = new Response('OK', { status: 200 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(result).toBe(response)
      expect(mockGetState).not.toHaveBeenCalled()
    })

    it('attempts refresh on 401 and retries request', async () => {
      const retryResponse = new Response('OK', { status: 200 })
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(retryResponse)

      mockGetState
        .mockReturnValueOnce({
          refresh: mockRefresh,
        })
        .mockReturnValueOnce({
          accessToken: 'refreshed-token',
        })
      mockRefresh.mockResolvedValueOnce(undefined)

      const request = new Request('https://example.com/api')
      const response = new Response('Unauthorized', { status: 401 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(mockRefresh).toHaveBeenCalled()
      expect(result).toBe(retryResponse)

      const fetchCall = new Request(fetchSpy.mock.calls[0][0])
      expect(fetchCall.headers.get('Authorization')).toBe('Bearer refreshed-token')
    })

    it('clears auth and returns original response when refresh fails', async () => {
      mockGetState.mockReturnValueOnce({
        refresh: mockRefresh,
        clearAuth: mockClearAuth,
      })
      mockRefresh.mockRejectedValueOnce(new Error('Refresh failed'))

      const request = new Request('https://example.com/api')
      const response = new Response('Unauthorized', { status: 401 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(mockClearAuth).toHaveBeenCalled()
      expect(result).toBe(response)
    })

    it('does not retry again when retried request also returns 401', async () => {
      const retry401Response = new Response('Unauthorized', { status: 401 })
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(retry401Response)

      mockGetState
        .mockReturnValueOnce({
          refresh: mockRefresh,
        })
        .mockReturnValueOnce({
          accessToken: 'refreshed-token',
        })
      mockRefresh.mockResolvedValueOnce(undefined)

      const request = new Request('https://example.com/api')
      const response = new Response('Unauthorized', { status: 401 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(mockRefresh).toHaveBeenCalledOnce()
      expect(result).toBe(retry401Response)

      const fetchCall = new Request(fetchSpy.mock.calls[0][0])
      expect(fetchCall.headers.get('X-Auth-Retry')).toBe('1')
    })

    it('skips refresh when request has X-Auth-Retry header', async () => {
      const request = new Request('https://example.com/api', {
        headers: { 'X-Auth-Retry': '1' },
      })
      const response = new Response('Unauthorized', { status: 401 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(result).toBe(response)
      expect(mockRefresh).not.toHaveBeenCalled()
    })

    it('returns original response when refresh succeeds but no token', async () => {
      mockGetState
        .mockReturnValueOnce({
          refresh: mockRefresh,
        })
        .mockReturnValueOnce({
          accessToken: null,
        })
      mockRefresh.mockResolvedValueOnce(undefined)

      const request = new Request('https://example.com/api')
      const response = new Response('Unauthorized', { status: 401 })

      const result = await authMiddleware.onResponse!({ request, response } as Parameters<
        NonNullable<typeof authMiddleware.onResponse>
      >[0])

      expect(result).toBe(response)
    })
  })
})
