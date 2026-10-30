import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AlertProvider } from '../../providers/alerts'

import { useExecutionTargetActions } from './useExecutionTargetActions'

const mockDeleteMutate = vi.fn()

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useMutation: vi.fn(() => ({ mutate: mockDeleteMutate, isPending: false })),
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
  id: 'et-002',
  cluster_id: 'cl-002',
  name: 'Staging OpenShift',
  backend_type: 'kubernetes',
  endpoint: 'https://api.staging.example.com',
  placement: {
    type: 'kubernetes' as const,
    namespace: 'syntara-staging',
    node_selectors: [] as string[],
    tolerations: [] as string[],
  },
  status: 'active',
  enabled: true,
  is_default: false,
  status_message: null,
  labels: {},
  created_at: '2026-01-02T00:00:00Z',
  last_ran_at: null,
}

type DeleteCallbacks = {
  onSuccess: () => void
  onError: (error: unknown) => void
  onSettled: () => void
}

describe('useExecutionTargetActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls DELETE with the target id and invokes onSuccess after 202', () => {
    const onSuccess = vi.fn()
    mockDeleteMutate.mockImplementation((_params: unknown, callbacks?: DeleteCallbacks) => {
      callbacks?.onSuccess()
      callbacks?.onSettled()
    })

    const { result } = renderHook(() => useExecutionTargetActions({ onSuccess }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.deleteDialog.open(target)
    })
    act(() => {
      result.current.handleDelete()
    })

    expect(mockDeleteMutate).toHaveBeenCalledWith(
      { params: { path: { target_id: 'et-002' } } },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown as () => void,
        onError: expect.any(Function) as unknown as (error: unknown) => void,
      })
    )
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(result.current.deleteDialog.isOpen).toBe(false)
  })

  it('does not call onSuccess on 409 conflict and closes the dialog', () => {
    const onSuccess = vi.fn()
    mockDeleteMutate.mockImplementation((_params: unknown, callbacks?: DeleteCallbacks) => {
      callbacks?.onError({
        status: 409,
        detail: 'Cannot delete the default execution target; promote another target first',
      })
      callbacks?.onSettled()
    })

    const { result } = renderHook(() => useExecutionTargetActions({ onSuccess }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.deleteDialog.open({
        ...target,
        id: 'et-001',
        name: 'Prod OpenShift West',
        is_default: true,
      })
    })
    act(() => {
      result.current.handleDelete()
    })

    expect(onSuccess).not.toHaveBeenCalled()
    expect(result.current.deleteDialog.isOpen).toBe(false)
  })
})
