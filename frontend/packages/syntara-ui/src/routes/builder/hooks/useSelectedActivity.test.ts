import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ActivityState } from '../../workflows/execution/types'

import { useSelectedActivity } from './useSelectedActivity'

function makeActivityState(overrides: Partial<ActivityState> & { activityId: string }): ActivityState {
  return { status: 'completed', ...overrides }
}

function makeDefaults(overrides: Partial<Parameters<typeof useSelectedActivity>[0]> = {}) {
  return {
    selectedNodeId: null as string | null | undefined,
    selectedNodeNameProp: null as string | null | undefined,
    activityStates: new Map<string, ActivityState>(),
    activityOrder: [] as { id: string; name: string; type?: string }[],
    nameMap: new Map<string, string>(),
    onNodeSelect: undefined as ((nodeId: string, nodeName: string) => void) | undefined,
    ...overrides,
  }
}

describe('useSelectedActivity', () => {
  describe('resolvedNodeId', () => {
    it('returns null when selectedNodeId is null', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults()))

      expect(result.current.resolvedNodeId).toBeNull()
    })

    it('returns null when selectedNodeId is undefined', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults({ selectedNodeId: undefined })))

      expect(result.current.resolvedNodeId).toBeNull()
    })

    it('returns the node ID when provided', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults({ selectedNodeId: 'task-1' })))

      expect(result.current.resolvedNodeId).toBe('task-1')
    })
  })

  describe('effectiveKey', () => {
    it('defaults to selectedNodeId when no activity key is selected', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults({ selectedNodeId: 'task-1' })))

      expect(result.current.effectiveKey).toBe('task-1')
    })

    it('uses composite key after handleRowClick for same base node', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            activityOrder: [{ id: 'task-1#iter-2', name: 'Task 1 (iter 2)' }],
          })
        )
      )

      act(() => {
        result.current.handleRowClick('task-1#iter-2', 'Task 1 (iter 2)')
      })

      expect(result.current.effectiveKey).toBe('task-1#iter-2')
    })

    it('uses selectedActivityKey when selectedNodeId is null', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            activityOrder: [{ id: 'task-1', name: 'Task 1' }],
          })
        )
      )

      act(() => {
        result.current.handleRowClick('task-1', 'Task 1')
      })

      expect(result.current.effectiveKey).toBe('task-1')
      expect(result.current.resolvedNodeId).toBe('task-1')
    })

    it('ignores composite key when base does not match selectedNodeId', () => {
      const onNodeSelect = vi.fn()
      const { result, rerender } = renderHook(
        ({ nodeId }: { nodeId: string }) =>
          useSelectedActivity(
            makeDefaults({
              selectedNodeId: nodeId,
              activityOrder: [
                { id: 'task-1#iter-1', name: 'Task 1 (iter 1)' },
                { id: 'task-2', name: 'Task 2' },
              ],
              onNodeSelect,
            })
          ),
        { initialProps: { nodeId: 'task-1' } }
      )

      act(() => {
        result.current.handleRowClick('task-1#iter-1', 'Task 1 (iter 1)')
      })
      expect(result.current.effectiveKey).toBe('task-1#iter-1')

      rerender({ nodeId: 'task-2' })
      expect(result.current.effectiveKey).toBe('task-2')
    })
  })

  describe('node change resets selection', () => {
    it('clears selectedActivityKey when selectedNodeId changes', () => {
      const { result, rerender } = renderHook(
        ({ nodeId }: { nodeId: string }) =>
          useSelectedActivity(
            makeDefaults({
              selectedNodeId: nodeId,
              activityOrder: [{ id: 'task-1#iter-1', name: 'Iter 1' }],
            })
          ),
        { initialProps: { nodeId: 'task-1' } }
      )

      act(() => {
        result.current.handleRowClick('task-1#iter-1', 'Iter 1')
      })
      expect(result.current.effectiveKey).toBe('task-1#iter-1')

      rerender({ nodeId: 'task-2' })
      expect(result.current.effectiveKey).toBe('task-2')
    })
  })

  describe('displayNodeName', () => {
    it('prefers selectedNodeNameProp when provided', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            selectedNodeNameProp: 'Prop Name',
            nameMap: new Map([['task-1', 'Map Name']]),
          })
        )
      )

      expect(result.current.displayNodeName).toBe('Prop Name')
    })

    it('falls back to matched activity name', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            activityOrder: [{ id: 'task-1', name: 'Activity Name' }],
          })
        )
      )

      expect(result.current.displayNodeName).toBe('Activity Name')
    })

    it('falls back to nameMap via resolveNodeName', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            nameMap: new Map([['task-1', 'Name Map Entry']]),
          })
        )
      )

      expect(result.current.displayNodeName).toBe('Name Map Entry')
    })

    it('falls back to node ID when no other name source matches', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults({ selectedNodeId: 'task-unknown' })))

      expect(result.current.displayNodeName).toBe('task-unknown')
    })
  })

  describe('selectedNodeState', () => {
    it('returns activity state for the effective key', () => {
      const state = makeActivityState({ activityId: 'task-1', status: 'running' })
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            activityStates: new Map([['task-1', state]]),
          })
        )
      )

      expect(result.current.selectedNodeState).toBe(state)
    })

    it('returns undefined when no state exists for the key', () => {
      const { result } = renderHook(() => useSelectedActivity(makeDefaults({ selectedNodeId: 'task-1' })))

      expect(result.current.selectedNodeState).toBeUndefined()
    })
  })

  describe('handleRowClick', () => {
    it('calls onNodeSelect with baseId from composite key', () => {
      const onNodeSelect = vi.fn()
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            onNodeSelect,
          })
        )
      )

      act(() => {
        result.current.handleRowClick('task-1#iter-3', 'Task 1 (iter 3)')
      })

      expect(onNodeSelect).toHaveBeenCalledWith('task-1', 'Task 1 (iter 3)')
    })

    it('calls onNodeSelect with plain key when no composite separator', () => {
      const onNodeSelect = vi.fn()
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
            onNodeSelect,
          })
        )
      )

      act(() => {
        result.current.handleRowClick('task-1', 'Task 1')
      })

      expect(onNodeSelect).toHaveBeenCalledWith('task-1', 'Task 1')
    })

    it('does not throw when onNodeSelect is undefined', () => {
      const { result } = renderHook(() =>
        useSelectedActivity(
          makeDefaults({
            selectedNodeId: 'task-1',
          })
        )
      )

      expect(() => {
        act(() => {
          result.current.handleRowClick('task-1#iter-1', 'Task 1')
        })
      }).not.toThrow()
    })
  })
})
