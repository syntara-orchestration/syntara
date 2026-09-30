import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { settingsFetchClient } from '../../../client'

import { useAllSettings } from './useAllSettings'

vi.mock('../../../client', () => ({
  settingsFetchClient: {
    GET: vi.fn(),
  },
  settingsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

describe('useAllSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useAllSettings({ enabled: false }), { wrapper })

    expect(result.current.settings).toEqual([])
    expect(result.current.isLoading).toBe(false)
    expect(vi.mocked(settingsFetchClient.GET)).not.toHaveBeenCalled()
  })

  it('returns settings on successful fetch', async () => {
    const mockSettings = [
      {
        id: '1',
        key: 'app.debug',
        name: 'Debug',
        description: null,
        helper_text: null,
        depends_on: null,
        category: 'application',
        group: 'General',
        value: null,
        default_value: false,
        effective_value: false,
        value_type: 'boolean' as const,
        requires_restart: false,
        cache_ttl_seconds: null,
        validation_schema: null,
        version: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    const mockResponse = {
      data: { resources: mockSettings },
      error: undefined,
      response: new Response(),
    } satisfies Awaited<ReturnType<typeof settingsFetchClient.GET>>

    vi.mocked(settingsFetchClient.GET).mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useAllSettings(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.settings).toEqual(mockSettings)
    expect(result.current.error).toBeNull()
  })

  it('paginates through multiple pages', async () => {
    const page1 = [
      {
        id: '1',
        key: 'a',
        name: 'A',
        description: null,
        helper_text: null,
        depends_on: null,
        category: 'c',
        group: 'g',
        value: null,
        default_value: 1,
        effective_value: 1,
        value_type: 'integer' as const,
        requires_restart: false,
        cache_ttl_seconds: null,
        validation_schema: null,
        version: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]
    const page2 = [
      {
        id: '2',
        key: 'b',
        name: 'B',
        description: null,
        helper_text: null,
        depends_on: null,
        category: 'c',
        group: 'g',
        value: null,
        default_value: 2,
        effective_value: 2,
        value_type: 'integer' as const,
        requires_restart: false,
        cache_ttl_seconds: null,
        validation_schema: null,
        version: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    const mockResponse1 = {
      data: { resources: page1, next: 'c1' },
      error: undefined,
      response: new Response(),
    } satisfies Awaited<ReturnType<typeof settingsFetchClient.GET>>

    const mockResponse2 = {
      data: { resources: page2 },
      error: undefined,
      response: new Response(),
    } satisfies Awaited<ReturnType<typeof settingsFetchClient.GET>>

    vi.mocked(settingsFetchClient.GET).mockResolvedValueOnce(mockResponse1).mockResolvedValueOnce(mockResponse2)

    const { result } = renderHook(() => useAllSettings(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.settings).toEqual([...page1, ...page2])
    expect(settingsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('returns error when fetch fails', async () => {
    const mockResponse = {
      data: undefined,
      error: { type: 'error', title: 'Forbidden', detail: 'Forbidden', code: 'FORBIDDEN', retryable: false },
      response: new Response(null, { status: 403 }),
    } satisfies Awaited<ReturnType<typeof settingsFetchClient.GET>>

    vi.mocked(settingsFetchClient.GET).mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useAllSettings(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
  })

  it('passes correct query parameters', async () => {
    const mockResponse = {
      data: { resources: [] },
      error: undefined,
      response: new Response(),
    } satisfies Awaited<ReturnType<typeof settingsFetchClient.GET>>

    vi.mocked(settingsFetchClient.GET).mockResolvedValue(mockResponse)

    renderHook(() => useAllSettings(), { wrapper })

    await waitFor(() => {
      expect(settingsFetchClient.GET).toHaveBeenCalledWith('/settings', {
        params: { query: { limit: 100, cursor: undefined } },
      })
    })
  })
})
