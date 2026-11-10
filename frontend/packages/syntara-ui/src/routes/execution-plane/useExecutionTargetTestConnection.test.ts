import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, screen, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AlertProvider } from '../../providers/alerts'

import { useExecutionTargetTestConnection } from './useExecutionTargetTestConnection'

const mockProbeMutate = vi.fn()

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useMutation: vi.fn(() => ({ mutate: mockProbeMutate, isPending: false })),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, createElement(AlertProvider, null, children))
  }
}

const target = {
  id: 'et-001',
  cluster_id: 'cl-001',
  name: 'Prod OpenShift West',
  backend_type: 'kubernetes' as const,
  endpoint: 'https://api.west.example.com',
  placement: {
    type: 'kubernetes' as const,
    namespace: 'syntara-workers',
    node_selectors: [] as string[],
    tolerations: [] as string[],
  },
  status: 'active' as const,
  enabled: true,
  is_default: true,
  status_message: null,
  labels: {},
  created_at: '2026-01-01T00:00:00Z',
  last_ran_at: null,
}

type ProbeCallbacks = {
  onSuccess?: (result: { healthy: boolean; message?: string | null; skipped?: boolean }) => void
  onError?: (error: unknown) => void
  onSettled?: () => void
}

describe('useExecutionTargetTestConnection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a success toast when the health request succeeds', async () => {
    mockProbeMutate.mockImplementation((_params: unknown, callbacks?: ProbeCallbacks) => {
      callbacks?.onSuccess?.({ healthy: true, message: null, skipped: false })
      callbacks?.onSettled?.()
    })

    const { result } = renderHook(() => useExecutionTargetTestConnection(), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.testConnection(target)
    })

    expect(mockProbeMutate).toHaveBeenCalledWith(
      { params: { path: { target_id: 'et-001' } } },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown as () => void,
        onError: expect.any(Function) as unknown as (error: unknown) => void,
      })
    )

    expect(await screen.findByText('Connection successful')).toBeInTheDocument()
    expect(
      await screen.findByText('Successfully connected to execution target "Prod OpenShift West".')
    ).toBeInTheDocument()
  })

  it('shows the failure reason when the health request returns unhealthy', async () => {
    mockProbeMutate.mockImplementation((_params: unknown, callbacks?: ProbeCallbacks) => {
      callbacks?.onSuccess?.({
        healthy: false,
        message: 'TLS handshake timed out',
        skipped: false,
      })
      callbacks?.onSettled?.()
    })

    const { result } = renderHook(() => useExecutionTargetTestConnection(), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.testConnection(target)
    })

    expect(await screen.findByText('Connection failed')).toBeInTheDocument()
    expect(await screen.findByText('TLS handshake timed out')).toBeInTheDocument()
  })

  it('shows a danger toast when the health request errors', async () => {
    mockProbeMutate.mockImplementation((_params: unknown, callbacks?: ProbeCallbacks) => {
      callbacks?.onError?.({ status: 409, detail: 'Cluster not ready' })
      callbacks?.onSettled?.()
    })

    const { result } = renderHook(() => useExecutionTargetTestConnection(), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.testConnection(target)
    })

    expect(await screen.findByText('Connection failed')).toBeInTheDocument()
    expect(await screen.findByText('Cluster not ready')).toBeInTheDocument()
  })

  it('ignores repeated clicks for the same target while its request is pending', async () => {
    const settleByTarget = new Map<string, () => void>()
    mockProbeMutate.mockImplementation(
      (params: { params: { path: { target_id: string } } }, callbacks?: ProbeCallbacks) => {
        const targetId = params.params.path.target_id
        settleByTarget.set(targetId, () => {
          callbacks?.onSuccess?.({ healthy: true, message: null, skipped: false })
          callbacks?.onSettled?.()
        })
      }
    )

    const { result } = renderHook(() => useExecutionTargetTestConnection(), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.testConnection(target)
    })

    expect(result.current.isTestingTarget('et-001')).toBe(true)
    expect(result.current.isTestingTarget('et-002')).toBe(false)

    act(() => {
      result.current.testConnection(target)
    })

    expect(mockProbeMutate).toHaveBeenCalledTimes(1)

    act(() => {
      result.current.testConnection({ ...target, id: 'et-002', name: 'Other' })
    })

    expect(mockProbeMutate).toHaveBeenCalledTimes(2)
    expect(result.current.isTestingTarget('et-002')).toBe(true)

    act(() => {
      settleByTarget.get('et-001')?.()
    })

    await waitFor(() => {
      expect(result.current.isTestingTarget('et-001')).toBe(false)
    })
    expect(result.current.isTestingTarget('et-002')).toBe(true)

    act(() => {
      settleByTarget.get('et-002')?.()
    })

    await waitFor(() => {
      expect(result.current.isTestingTarget('et-002')).toBe(false)
    })
  })
})
