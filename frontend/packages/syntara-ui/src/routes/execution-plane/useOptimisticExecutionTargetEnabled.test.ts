import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useOptimisticExecutionTargetEnabled } from './useOptimisticExecutionTargetEnabled'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

function makeTarget(overrides: Partial<ExecutionTarget> & Pick<ExecutionTarget, 'id' | 'enabled'>): ExecutionTarget {
  return {
    cluster_id: 'cl-001',
    name: 'Test target',
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

describe('useOptimisticExecutionTargetEnabled', () => {
  it('optimistically enables a target before the patch resolves', async () => {
    let resolvePatch!: (value: unknown) => void
    const patchTarget = vi.fn(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve
        })
    )
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const onError = vi.fn()
    const target = makeTarget({ id: 'et-1', enabled: false })

    const { result, rerender } = renderHook(
      ({ targets }) =>
        useOptimisticExecutionTargetEnabled({
          targets,
          patchTarget,
          onSuccess,
          onError,
        }),
      { initialProps: { targets: [target] } }
    )

    act(() => {
      result.current.setTargetEnabled(target, true)
    })

    await waitFor(() => {
      expect(result.current.targets[0]?.enabled).toBe(true)
    })
    expect(patchTarget).toHaveBeenCalledWith({
      params: { path: { target_id: 'et-1' } },
      body: { enabled: true },
    })

    await act(async () => {
      resolvePatch({})
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
    })

    rerender({ targets: [makeTarget({ id: 'et-1', enabled: true })] })
    expect(result.current.targets[0]?.enabled).toBe(true)
    expect(onError).not.toHaveBeenCalled()
  })

  it('rolls back optimistic enable when the patch fails', async () => {
    const patchTarget = vi.fn().mockRejectedValue(new Error('Server error'))
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const target = makeTarget({ id: 'et-1', enabled: false })

    const { result } = renderHook(() =>
      useOptimisticExecutionTargetEnabled({
        targets: [target],
        patchTarget,
        onSuccess,
        onError,
      })
    )

    act(() => {
      result.current.setTargetEnabled(target, true)
    })

    await waitFor(() => {
      expect(result.current.targets[0]?.enabled).toBe(true)
    })

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Failed to enable execution target', expect.any(Error))
    })

    await waitFor(() => {
      expect(result.current.targets[0]?.enabled).toBe(false)
    })
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('optimistically disables and reports disable errors', async () => {
    const patchTarget = vi.fn().mockRejectedValue(new Error('Nope'))
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const target = makeTarget({ id: 'et-2', enabled: true })

    const { result } = renderHook(() =>
      useOptimisticExecutionTargetEnabled({
        targets: [target],
        patchTarget,
        onSuccess,
        onError,
      })
    )

    act(() => {
      result.current.setTargetEnabled(target, false)
    })

    await waitFor(() => {
      expect(result.current.targets[0]?.enabled).toBe(false)
    })

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Failed to disable execution target', expect.any(Error))
    })

    await waitFor(() => {
      expect(result.current.targets[0]?.enabled).toBe(true)
    })
  })

  it('no-ops when the target has no id', () => {
    const patchTarget = vi.fn()
    const { result } = renderHook(() =>
      useOptimisticExecutionTargetEnabled({
        targets: [makeTarget({ id: 'et-1', enabled: false })],
        patchTarget,
        onSuccess: vi.fn(),
        onError: vi.fn(),
      })
    )

    act(() => {
      result.current.setTargetEnabled({ ...makeTarget({ id: 'et-1', enabled: false }), id: '' }, true)
    })

    expect(patchTarget).not.toHaveBeenCalled()
  })
})
