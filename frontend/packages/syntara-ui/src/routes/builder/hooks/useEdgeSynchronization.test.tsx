import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { useEdgeSynchronization } from './useEdgeSynchronization'

// Mock dependencies
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      currentWorkflow: { triggers: [] },
      reorderActivitiesFromEdges: vi.fn(),
    })),
  },
}))

vi.mock('../utils/filterHelpers', () => ({
  isButtonEdge: (edge: { type?: string; id?: string }) => edge.type === 'buttonEdge' || edge.id?.startsWith('button-'),
}))

describe('useEdgeSynchronization', () => {
  const mockSetStoredEdges = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does nothing when not initialized', () => {
    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    renderHook(() =>
      useEdgeSynchronization({
        edges: edges,
        isInitialized: false,
        setStoredEdges: mockSetStoredEdges,
        workflowVersion: 1,
      })
    )

    expect(mockSetStoredEdges).not.toHaveBeenCalled()
  })

  it('skips first sync to avoid setting isDirty', () => {
    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    renderHook(() =>
      useEdgeSynchronization({
        edges: edges,
        isInitialized: true,
        setStoredEdges: mockSetStoredEdges,
        workflowVersion: 1,
      })
    )

    expect(mockSetStoredEdges).not.toHaveBeenCalled()
  })

  it('filters out button edges', () => {
    const edges = [
      { id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' },
      { id: 'button-node-1', source: 'node-1', target: 'placeholder', type: 'buttonEdge' },
    ]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger second render with changed edges including a button edge to filter
    const newEdges = [
      { id: 'edge-2', source: 'node-2', target: 'node-3', type: 'default' },
      { id: 'button-node-2', source: 'node-2', target: 'placeholder', type: 'buttonEdge' },
    ]
    rerender({ edges: newEdges })

    expect(mockSetStoredEdges).toHaveBeenCalled()
    const calledWith = mockSetStoredEdges.mock.calls[0][0] as { id: string }[]
    // Verify button edges were filtered out
    expect(calledWith.every((e) => !e.id.startsWith('button-'))).toBe(true)
  })

  it('filters out placeholder edges', () => {
    const edges = [
      { id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' },
      { id: 'edge-2', source: 'placeholder-1', target: 'node-2', type: 'default' },
      { id: 'edge-3', source: 'node-1', target: 'placeholder-2', type: 'default' },
    ]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger change with edges including placeholders to filter
    const newEdges = [
      { id: 'edge-new', source: 'node-3', target: 'node-4', type: 'default' },
      { id: 'edge-placeholder', source: 'placeholder-x', target: 'node-5', type: 'default' },
    ]
    rerender({ edges: newEdges })

    expect(mockSetStoredEdges).toHaveBeenCalled()
    const calledWith = mockSetStoredEdges.mock.calls[0][0] as { source: string; target: string }[]
    // Verify placeholder edges were filtered out
    expect(calledWith.every((e) => !e.source.startsWith('placeholder') && !e.target.startsWith('placeholder'))).toBe(
      true
    )
  })

  it('returns refs for testing', () => {
    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    const { result } = renderHook(() =>
      useEdgeSynchronization({
        edges: edges,
        isInitialized: true,
        setStoredEdges: mockSetStoredEdges,
        workflowVersion: 1,
      })
    )

    expect(result.current.lastEdgesSignatureRef).toBeDefined()
    expect(result.current.isSyncingRef).toBeDefined()
  })

  it('does not sync when edges have not changed', () => {
    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // First pass (isFirstSync = true, sets signature)
    // Second pass with same edges
    rerender({ edges })

    // Still should not have been called (first sync skipped, second had no changes)
    expect(mockSetStoredEdges).not.toHaveBeenCalled()
  })

  it('transforms trigger display IDs to real IDs for source', () => {
    // Mock workflow store with trigger that has real ID
    const mockTrigger = { id: 'real-trigger-id-123', type: 'manual_trigger' }
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      currentWorkflow: { triggers: [mockTrigger] },
      reorderActivitiesFromEdges: vi.fn(),
    } as never)

    const edges = [{ id: 'edge-1', source: 'trigger-0', target: 'node-2', type: 'default' }]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger second render to invoke setStoredEdges
    const newEdges = [{ id: 'edge-2', source: 'trigger-0', target: 'node-3', type: 'default' }]
    rerender({ edges: newEdges })

    expect(mockSetStoredEdges).toHaveBeenCalled()
    const calledWith = mockSetStoredEdges.mock.calls[0][0] as { source: string }[]
    // Verify display ID was transformed to real ID
    expect(calledWith[0].source).toBe('real-trigger-id-123')
  })

  it('transforms trigger display IDs to real IDs for target', () => {
    // Mock workflow store with trigger that has real ID
    const mockTrigger = { id: 'real-trigger-id-456', type: 'manual_trigger' }
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      currentWorkflow: { triggers: [mockTrigger] },
      reorderActivitiesFromEdges: vi.fn(),
    } as never)

    const edges = [{ id: 'edge-1', source: 'node-1', target: 'trigger-0', type: 'default' }]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger second render to invoke setStoredEdges
    const newEdges = [{ id: 'edge-2', source: 'node-2', target: 'trigger-0', type: 'default' }]
    rerender({ edges: newEdges })

    expect(mockSetStoredEdges).toHaveBeenCalled()
    const calledWith = mockSetStoredEdges.mock.calls[0][0] as { target: string }[]
    // Verify display ID was transformed to real ID
    expect(calledWith[0].target).toBe('real-trigger-id-456')
  })

  it('calls reorderActivitiesFromEdges when edges change', () => {
    const mockReorderActivities = vi.fn()

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      currentWorkflow: { triggers: [] },
      reorderActivitiesFromEdges: mockReorderActivities,
    } as never)

    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger second render with different edges
    const newEdges = [{ id: 'edge-2', source: 'node-3', target: 'node-4', type: 'default' }]
    rerender({ edges: newEdges })

    expect(mockReorderActivities).toHaveBeenCalled()
  })

  it('prevents re-entrant syncing with isSyncingRef guard', async () => {
    const mockReorderActivities = vi.fn()

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      currentWorkflow: { triggers: [] },
      reorderActivitiesFromEdges: mockReorderActivities,
    } as never)

    const edges = [{ id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' }]

    const { result, rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger second render with different edges
    const newEdges = [{ id: 'edge-2', source: 'node-3', target: 'node-4', type: 'default' }]
    rerender({ edges: newEdges })

    // While syncing flag is true, trigger another render
    expect(result.current.isSyncingRef.current).toBe(true)

    const anotherEdges = [{ id: 'edge-3', source: 'node-5', target: 'node-6', type: 'default' }]
    rerender({ edges: anotherEdges })

    // reorderActivities should only be called once (second call prevented by guard)
    expect(mockReorderActivities).toHaveBeenCalledTimes(1)

    // Wait for microtask to clear syncing flag
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(result.current.isSyncingRef.current).toBe(false)
  })

  it('filters out pending edges', () => {
    const edges = [
      { id: 'edge-1', source: 'node-1', target: 'node-2', type: 'default' },
      { id: 'pending-edge', source: 'node-1', target: 'node-3', type: 'default' },
      { id: 'edge-2', source: 'pending-target-1', target: 'node-4', type: 'default' },
    ]

    const { rerender } = renderHook(
      ({ edges }) =>
        useEdgeSynchronization({
          edges: edges,
          isInitialized: true,
          setStoredEdges: mockSetStoredEdges,
          workflowVersion: 1,
        }),
      { initialProps: { edges } }
    )

    // Trigger change
    const newEdges = [
      { id: 'edge-new', source: 'node-5', target: 'node-6', type: 'default' },
      { id: 'pending-new', source: 'node-7', target: 'node-8', type: 'default' },
    ]
    rerender({ edges: newEdges })

    expect(mockSetStoredEdges).toHaveBeenCalled()
    const calledWith = mockSetStoredEdges.mock.calls[0][0] as { id: string; source: string; target: string }[]

    // Verify pending edges were filtered out
    expect(calledWith.every((e) => !e.id.startsWith('pending-'))).toBe(true)
    expect(calledWith.every((e) => !e.source.startsWith('pending-target-'))).toBe(true)
    expect(calledWith.every((e) => !e.target.startsWith('pending-target-'))).toBe(true)
  })
})
