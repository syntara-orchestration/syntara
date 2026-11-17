import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanSubmitFormPrompt } from './useCanSubmitFormPrompt'

vi.mock('../../../stores/useAuthStore', () => ({
  useAuthStore: (selector: (state: { userId: string | null }) => unknown) => selector({ userId: 'user-1' }),
}))

const mockUseQuery = vi.fn()

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQuery: (...args: unknown[]) =>
      mockUseQuery(...args) as {
        isLoading: boolean
        isError: boolean
        data: unknown
        refetch: ReturnType<typeof vi.fn>
      },
  }
})

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useCanSubmitFormPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
      refetch: vi.fn(),
    })
  })

  it('allows submit when no responders are configured', () => {
    const { result } = renderHook(() => useCanSubmitFormPrompt({ responder_users: [], responder_groups: [] }), {
      wrapper: createWrapper(),
    })

    expect(result.current.canSubmit).toBe(true)
    expect(result.current.isLoading).toBe(false)
  })

  it('allows submit when current user is a direct responder', () => {
    const { result } = renderHook(
      () =>
        useCanSubmitFormPrompt({
          responder_users: [{ id: 'user-1', username: 'me' }],
          responder_groups: [],
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.canSubmit).toBe(true)
  })

  it('denies submit when user is not in responder list', () => {
    const { result } = renderHook(
      () =>
        useCanSubmitFormPrompt({
          responder_users: [{ id: 'other-user', username: 'other' }],
          responder_groups: [],
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.canSubmit).toBe(false)
  })

  it('returns false when prompt is undefined', () => {
    const { result } = renderHook(() => useCanSubmitFormPrompt(undefined), { wrapper: createWrapper() })
    expect(result.current.canSubmit).toBe(false)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isError).toBe(false)
  })

  it('returns false when responder fields are absent on prompt', () => {
    const { result } = renderHook(() => useCanSubmitFormPrompt({ name: 'x' } as never), { wrapper: createWrapper() })
    expect(result.current.canSubmit).toBe(false)
  })

  it('reports loading while group membership is fetched', () => {
    mockUseQuery.mockReturnValue({ isLoading: true, data: undefined, isError: false, refetch: vi.fn() })

    const { result } = renderHook(
      () =>
        useCanSubmitFormPrompt({
          responder_users: [],
          responder_groups: [{ id: 'group-a', name: 'Ops' }],
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.canSubmit).toBe(false)
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isError).toBe(false)
  })

  it('allows submit when user belongs to a responder group', async () => {
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [{ id: 'group-a' }],
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useCanSubmitFormPrompt({
          responder_users: [],
          responder_groups: [{ id: 'group-a', name: 'Ops' }],
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.canSubmit).toBe(true)
    })
  })
})
