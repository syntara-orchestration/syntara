import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { workflowClient } from '../../client'

import { useVisibleUsedByCounts, useWorkflowUsedBy, useWorkflowUsedByCounts } from './useWorkflowUsedBy'

vi.mock('../../client', () => ({
  workflowClient: { useQuery: vi.fn(() => ({ data: undefined, isLoading: false, error: null })) },
}))

const mockedUseQuery = vi.mocked(workflowClient.useQuery)

describe('useWorkflowUsedBy', () => {
  it('derives total count and referencing parents from the response', () => {
    mockedUseQuery.mockReturnValue({
      data: { referencing_parent_count: 3, resources: [{ id: 'p1', name: 'Parent 1' }], next: null, prev: null },
      isLoading: false,
      error: null,
    })

    const { result } = renderHook(() => useWorkflowUsedBy('wf-1'))

    expect(result.current.totalCount).toBe(3)
    expect(result.current.referencingParents).toHaveLength(1)
    expect(result.current.isError).toBe(false)
  })

  it('passes trigger_node_ids through to the query params', () => {
    renderHook(() => useWorkflowUsedBy('wf-1', { triggerNodeIds: ['trig_a', 'trig_b'] }))

    expect(mockedUseQuery).toHaveBeenLastCalledWith(
      'get',
      '/workflows/{workflow_id}/used_by',
      expect.objectContaining({
        params: { path: { workflow_id: 'wf-1' }, query: { trigger_node_ids: ['trig_a', 'trig_b'] } },
      }),
      expect.objectContaining({ enabled: true })
    )
  })

  it('passes cursor and limit through to the query params (backend cursor pagination)', () => {
    renderHook(() => useWorkflowUsedBy('wf-1', { cursor: 'c2', limit: 10 }))

    expect(mockedUseQuery).toHaveBeenLastCalledWith(
      'get',
      '/workflows/{workflow_id}/used_by',
      expect.objectContaining({
        params: { path: { workflow_id: 'wf-1' }, query: { cursor: 'c2', limit: 10 } },
      }),
      expect.objectContaining({ enabled: true })
    )
  })

  it('is disabled when no workflow id is provided', () => {
    renderHook(() => useWorkflowUsedBy(undefined))

    expect(mockedUseQuery).toHaveBeenLastCalledWith(
      'get',
      '/workflows/{workflow_id}/used_by',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })
})

describe('useWorkflowUsedByCounts / useVisibleUsedByCounts', () => {
  it('builds a map keyed by workflow id', () => {
    mockedUseQuery.mockReturnValue({
      data: {
        counts: [
          { workflow_id: 'a', referencing_parent_count: 2 },
          { workflow_id: 'b', referencing_parent_count: 0 },
        ],
      },
      isLoading: false,
      error: null,
    })

    const { result } = renderHook(() => useWorkflowUsedByCounts(['a', 'b']))

    expect(result.current.countsById.get('a')).toBe(2)
    expect(result.current.countsById.get('b')).toBe(0)
  })

  it('caps the visible id set at 100 and returns the counts map', () => {
    mockedUseQuery.mockReturnValue({
      data: { counts: [{ workflow_id: 'w0', referencing_parent_count: 5 }] },
      isLoading: false,
      error: null,
    })

    const workflows = Array.from({ length: 150 }, (_, index) => ({ id: `w${index}` }))
    const { result } = renderHook(() => useVisibleUsedByCounts(workflows))

    const lastCall = mockedUseQuery.mock.lastCall
    expect(lastCall?.[1]).toBe('/workflows/used_by_counts')
    const options = lastCall?.[2] as unknown as { params: { query: { workflow_ids: string[] } } } | undefined
    expect(options?.params.query.workflow_ids).toHaveLength(100)
    expect(result.current.get('w0')).toBe(5)
  })

  it('returns a stable counts map across re-renders when the data is unchanged', () => {
    const data = { counts: [{ workflow_id: 'a', referencing_parent_count: 1 }] }
    mockedUseQuery.mockReturnValue({ data, isLoading: false, error: null })

    const { result, rerender } = renderHook(() => useWorkflowUsedByCounts(['a']))
    const first = result.current.countsById
    rerender()
    expect(result.current.countsById).toBe(first)
  })
})
