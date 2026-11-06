import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AlertProvider } from '../../providers/alerts'

import { useExecutionTargetEnabledToggle } from './useExecutionTargetEnabledToggle'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

const mockMutateAsync = vi.fn()
let mockIsPending = false

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useMutation: vi.fn(() => ({
      mutateAsync: mockMutateAsync,
      get isPending() {
        return mockIsPending
      },
    })),
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

function makeTarget(overrides: Partial<ExecutionTarget> & Pick<ExecutionTarget, 'id' | 'enabled'>): ExecutionTarget {
  return {
    cluster_id: 'cl-001',
    name: 'Prod OpenShift West',
    backend_type: 'kubernetes',
    endpoint: 'https://api.example.com',
    placement: {
      type: 'kubernetes',
      namespace: 'syntara-workers',
      node_selectors: [],
      tolerations: [],
    },
    status: 'active',
    is_default: false,
    status_message: null,
    labels: {},
    created_at: '2026-01-01T00:00:00Z',
    last_ran_at: null,
    ...overrides,
  }
}

describe('useExecutionTargetEnabledToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPending = false
    mockMutateAsync.mockResolvedValue({})
  })

  it('opens the disable dialog when toggling an enabled target', () => {
    const target = makeTarget({ id: 'et-1', enabled: true })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess: vi.fn() }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.handleToggleEnabled(target)
    })

    expect(result.current.disableDialog.isOpen).toBe(true)
    expect(result.current.disableDialog.item).toEqual(target)
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('enables a disabled target immediately without confirmation', async () => {
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const target = makeTarget({ id: 'et-1', enabled: false })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.handleToggleEnabled(target)
    })

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        params: { path: { target_id: 'et-1' } },
        body: { enabled: true },
      })
    })
    expect(result.current.disableDialog.isOpen).toBe(false)

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
    })
  })

  it('patches enabled: false after confirming disable', async () => {
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const target = makeTarget({ id: 'et-1', enabled: true })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.disableDialog.open(target)
    })
    act(() => {
      result.current.handleDisable()
    })

    expect(result.current.disableDialog.isOpen).toBe(false)

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        params: { path: { target_id: 'et-1' } },
        body: { enabled: false },
      })
    })

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
    })
  })

  it('does not patch when confirming disable with no dialog item', () => {
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [], onSuccess: vi.fn() }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.handleDisable()
    })

    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('ignores enable toggles while a patch is pending', () => {
    mockIsPending = true
    const target = makeTarget({ id: 'et-1', enabled: false })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess: vi.fn() }), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPatchPending).toBe(true)

    act(() => {
      result.current.handleToggleEnabled(target)
    })

    expect(mockMutateAsync).not.toHaveBeenCalled()
    expect(result.current.disableDialog.isOpen).toBe(false)
  })

  it('ignores disable confirmation while a patch is pending', () => {
    mockIsPending = true
    const target = makeTarget({ id: 'et-1', enabled: true })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess: vi.fn() }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.disableDialog.open(target)
    })
    act(() => {
      result.current.handleDisable()
    })

    expect(mockMutateAsync).not.toHaveBeenCalled()
    // Pending guard returns before close — dialog stays open so the user can retry.
    expect(result.current.disableDialog.isOpen).toBe(true)
  })

  it('ignores opening the disable dialog while a patch is pending', () => {
    mockIsPending = true
    const target = makeTarget({ id: 'et-1', enabled: true })
    const { result } = renderHook(() => useExecutionTargetEnabledToggle({ targets: [target], onSuccess: vi.fn() }), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.handleToggleEnabled(target)
    })

    expect(result.current.disableDialog.isOpen).toBe(false)
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })
})
