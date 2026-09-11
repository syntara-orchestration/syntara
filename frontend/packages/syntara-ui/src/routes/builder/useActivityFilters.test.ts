import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FilterOperatorEnum } from '../../types/filters'
import type { ActivityState } from '../workflows/execution/types'

import type { ActivityOrderItem } from './ExecutionActivityTable'
import { useActivityFilters } from './useActivityFilters'

const ACTIVITIES: ActivityOrderItem[] = [
  { id: 'node-1', name: 'Process data', type: 'script' },
  { id: 'node-2', name: 'Check condition', type: 'condition' },
  { id: 'node-3', name: 'Send notification', type: 'http_request' },
  { id: 'node-4', name: 'Merge branches', type: 'converge' },
]

function buildStates(overrides?: Partial<Record<string, Partial<ActivityState>>>): Map<string, ActivityState> {
  const defaults: Record<string, ActivityState> = {
    'node-1': { activityId: 'node-1', status: 'completed' },
    'node-2': { activityId: 'node-2', status: 'running' },
    'node-3': { activityId: 'node-3', status: 'pending' },
    'node-4': { activityId: 'node-4', status: 'failed' },
  }
  if (overrides) {
    for (const [id, patch] of Object.entries(overrides)) {
      if (defaults[id]) {
        defaults[id] = { ...defaults[id], ...patch }
      }
    }
  }
  return new Map(Object.entries(defaults))
}

describe('useActivityFilters', () => {
  it('returns all activities when no filters are active', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    expect(result.current.filteredActivityOrder).toEqual(ACTIVITIES)
    expect(result.current.hasActiveFilters).toBe(false)
    expect(result.current.filters).toEqual([])
  })

  it('filters by keyword (case-insensitive)', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'name', operator: FilterOperatorEnum.CONTAINS, value: 'process' }])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(1)
    expect(result.current.filteredActivityOrder[0].id).toBe('node-1')
    expect(result.current.hasActiveFilters).toBe(true)
  })

  it('filters by node type', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'type', value: 'condition' }])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(1)
    expect(result.current.filteredActivityOrder[0].id).toBe('node-2')
  })

  it('filters by status', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'status', value: 'failed' }])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(1)
    expect(result.current.filteredActivityOrder[0].id).toBe('node-4')
  })

  it('combines multiple filters with AND logic', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([
        { key: 'name', operator: FilterOperatorEnum.CONTAINS, value: 'data' },
        { key: 'status', value: 'completed' },
      ])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(1)
    expect(result.current.filteredActivityOrder[0].id).toBe('node-1')
  })

  it('returns empty array when no activities match', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'name', operator: FilterOperatorEnum.CONTAINS, value: 'nonexistent' }])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(0)
    expect(result.current.hasActiveFilters).toBe(true)
  })

  it('clears filters and restores all activities', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'status', value: 'completed' }])
    })
    expect(result.current.filteredActivityOrder).toHaveLength(1)

    act(() => {
      result.current.handleFilterChange([])
    })
    expect(result.current.filteredActivityOrder).toEqual(ACTIVITIES)
    expect(result.current.hasActiveFilters).toBe(false)
  })

  it('uses activity id as fallback when name is undefined', () => {
    const activitiesWithoutName: ActivityOrderItem[] = [{ id: 'my-task-node', type: 'script' }]
    const states = new Map<string, ActivityState>([['my-task-node', { activityId: 'my-task-node', status: 'running' }]])
    const { result } = renderHook(() => useActivityFilters(activitiesWithoutName, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'name', operator: FilterOperatorEnum.CONTAINS, value: 'my-task' }])
    })

    expect(result.current.filteredActivityOrder).toHaveLength(1)
  })

  it('handles unknown filter keys gracefully', () => {
    const states = buildStates()
    const { result } = renderHook(() => useActivityFilters(ACTIVITIES, states))

    act(() => {
      result.current.handleFilterChange([{ key: 'unknown_key', value: 'something' }])
    })

    expect(result.current.filteredActivityOrder).toEqual(ACTIVITIES)
  })
})
