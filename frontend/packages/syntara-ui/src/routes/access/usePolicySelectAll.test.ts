import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SELECT_ALL_LOAD_ERROR } from './policySelectConstants'
import { usePolicySelectAll } from './usePolicySelectAll'

describe('usePolicySelectAll', () => {
  it('merges fetched policy names into the current selection', async () => {
    const onChange = vi.fn()
    const fetchPolicies = vi.fn().mockResolvedValue([
      { name: 'policy-a', is_project_eligible: false },
      { name: 'policy-b', is_project_eligible: false },
    ])

    const { result } = renderHook(() =>
      usePolicySelectAll({
        selected: ['policy-a'],
        onChange,
        fetchPolicies,
        showError: vi.fn(),
      })
    )

    act(() => {
      result.current.runSelectAll()
    })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['policy-a', 'policy-b'])
    })
  })

  it('shows an error alert when fetching policies fails', async () => {
    const showError = vi.fn()
    const fetchPolicies = vi.fn().mockRejectedValue(new Error('network'))

    const { result } = renderHook(() =>
      usePolicySelectAll({
        selected: [],
        onChange: vi.fn(),
        fetchPolicies,
        showError,
      })
    )

    act(() => {
      result.current.runSelectAll()
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith(SELECT_ALL_LOAD_ERROR)
    })
  })

  it('ignores duplicate runSelectAll calls while a fetch is in progress', async () => {
    let resolveFetch: (value: { name: string; is_project_eligible: boolean }[]) => void = () => undefined
    const fetchPolicies = vi.fn(
      () =>
        new Promise<{ name: string; is_project_eligible: boolean }[]>((resolve) => {
          resolveFetch = resolve
        })
    )

    const { result } = renderHook(() =>
      usePolicySelectAll({
        selected: [],
        onChange: vi.fn(),
        fetchPolicies,
        showError: vi.fn(),
      })
    )

    act(() => {
      result.current.runSelectAll()
      result.current.runSelectAll()
    })

    expect(fetchPolicies).toHaveBeenCalledTimes(1)
    expect(result.current.isSelectingAll).toBe(true)

    act(() => {
      resolveFetch([{ name: 'policy-a', is_project_eligible: false }])
    })

    await waitFor(() => {
      expect(result.current.isSelectingAll).toBe(false)
    })
  })

  it('merges against the latest selection when chips change during fetch', async () => {
    let resolveFetch: (value: { name: string; is_project_eligible: boolean }[]) => void = () => undefined
    const fetchPolicies = vi.fn(
      () =>
        new Promise<{ name: string; is_project_eligible: boolean }[]>((resolve) => {
          resolveFetch = resolve
        })
    )
    const onChange = vi.fn()

    const { result, rerender } = renderHook(
      ({ selected }: { selected: string[] }) =>
        usePolicySelectAll({
          selected,
          onChange,
          fetchPolicies,
          showError: vi.fn(),
        }),
      { initialProps: { selected: ['policy-a'] } }
    )

    act(() => {
      result.current.runSelectAll()
    })

    rerender({ selected: ['policy-c'] })

    act(() => {
      resolveFetch([
        { name: 'policy-a', is_project_eligible: false },
        { name: 'policy-b', is_project_eligible: false },
      ])
    })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['policy-c', 'policy-a', 'policy-b'])
    })
  })
})
