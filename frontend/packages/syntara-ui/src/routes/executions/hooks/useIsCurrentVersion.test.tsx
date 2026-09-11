import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'

import { workflowClient } from '../../../client'

import { useIsCurrentVersion } from './useIsCurrentVersion'

vi.mock('../../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  },
  authMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe('useIsCurrentVersion', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    })
  })

  it('returns isCurrentVersion true when no workflow data loaded', () => {
    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'v-1', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(true)
    expect(result.current.versionLabel).toBe('')
  })

  it('returns isCurrentVersion true when workflowVersionId is undefined', () => {
    const { result } = renderHook(() => useIsCurrentVersion('wf-1', undefined, true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(true)
  })

  it('returns isLoading true when queries are loading', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'v-1', true), { wrapper: Wrapper })

    expect(result.current.isLoading).toBe(true)
  })

  it('returns isCurrentVersion true when version IDs match', () => {
    const mockWorkflowQuery = {
      data: { version: { id: 'current-version-id' } },
      isLoading: false,
      error: null,
    }
    const mockVersionsQuery = {
      data: null,
      isLoading: false,
      error: null,
    }

    vi.mocked(workflowClient.useQuery).mockReturnValueOnce(mockWorkflowQuery).mockReturnValueOnce(mockVersionsQuery)

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'current-version-id', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(true)
    expect(result.current.versionLabel).toBe('')
    expect(result.current.isLoading).toBe(false)
  })

  it('returns isCurrentVersion false with name when version differs', () => {
    const mockWorkflowQuery = {
      data: { version: { id: 'current-version-id' } },
      isLoading: false,
      error: null,
    }
    const mockVersionsQuery = {
      data: {
        resources: [
          { id: 'old-version-id', name: 'Release v1.0', created_at: '2024-01-15T10:00:00Z' },
          { id: 'current-version-id', name: 'Release v2.0', created_at: '2024-02-15T10:00:00Z' },
        ],
      },
      isLoading: false,
      error: null,
    }

    vi.mocked(workflowClient.useQuery).mockReturnValueOnce(mockWorkflowQuery).mockReturnValueOnce(mockVersionsQuery)

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'old-version-id', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(false)
    expect(result.current.versionLabel).toBe('Release v1.0')
  })

  it('returns formatted date when name is null', () => {
    const mockWorkflowQuery = {
      data: { version: { id: 'current-version-id' } },
      isLoading: false,
      error: null,
    }
    const mockVersionsQuery = {
      data: {
        resources: [{ id: 'old-version-id', name: null, created_at: '2024-01-15T10:00:00Z' }],
      },
      isLoading: false,
      error: null,
    }

    vi.mocked(workflowClient.useQuery).mockReturnValueOnce(mockWorkflowQuery).mockReturnValueOnce(mockVersionsQuery)

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'old-version-id', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(false)
    expect(result.current.versionLabel).not.toBe('')
  })

  it('returns isLoading true when versions query is still loading for older version', () => {
    const mockWorkflowQuery = {
      data: { version: { id: 'current-version-id' } },
      isLoading: false,
      error: null,
    }
    const mockVersionsQuery = {
      data: null,
      isLoading: true,
      error: null,
    }

    vi.mocked(workflowClient.useQuery).mockReturnValueOnce(mockWorkflowQuery).mockReturnValueOnce(mockVersionsQuery)

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'old-version-id', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })

  it('handles version not found in versions list', () => {
    const mockWorkflowQuery = {
      data: { version: { id: 'current-version-id' } },
      isLoading: false,
      error: null,
    }
    const mockVersionsQuery = {
      data: { resources: [] },
      isLoading: false,
      error: null,
    }

    vi.mocked(workflowClient.useQuery).mockReturnValueOnce(mockWorkflowQuery).mockReturnValueOnce(mockVersionsQuery)

    const { result } = renderHook(() => useIsCurrentVersion('wf-1', 'missing-version-id', true), { wrapper: Wrapper })

    expect(result.current.isCurrentVersion).toBe(false)
  })
})
