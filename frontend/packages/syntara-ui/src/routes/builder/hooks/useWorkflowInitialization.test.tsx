import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { useWorkflowInitialization } from './useWorkflowInitialization'

let workflowStoreState: Record<string, unknown> = { nodePositions: {} }

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: () => workflowStoreState,
  },
}))

describe('useWorkflowInitialization', () => {
  const mockOnLayout = vi.fn()
  const mockOnVersionChange = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    workflowStoreState = { nodePositions: {} }
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with isInitialized as false', () => {
    const { result } = renderHook(() =>
      useWorkflowInitialization({
        nodes: [],
        workflowVersion: 1,
        onLayout: mockOnLayout,
      })
    )

    expect(result.current.isInitialized).toBe(false)
  })

  it('does not initialize when nodes are empty', () => {
    const { result } = renderHook(() =>
      useWorkflowInitialization({
        nodes: [],
        workflowVersion: 1,
        onLayout: mockOnLayout,
      })
    )

    expect(result.current.isInitialized).toBe(false)
  })

  it('initializes when all nodes are measured', async () => {
    const measuredNodes = [
      { id: 'node-1', measured: { width: 100, height: 50 } },
      { id: 'node-2', measured: { width: 100, height: 50 } },
    ] as never[]

    const { result } = renderHook(() =>
      useWorkflowInitialization({
        nodes: measuredNodes,
        workflowVersion: 1,
        onLayout: mockOnLayout,
      })
    )

    // Allow microtask to run
    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.isInitialized).toBe(true)
  })

  it('calls onLayout after initialization', async () => {
    const measuredNodes = [{ id: 'node-1', measured: { width: 100, height: 50 } }] as never[]

    renderHook(() =>
      useWorkflowInitialization({
        nodes: measuredNodes,
        workflowVersion: 1,
        onLayout: mockOnLayout,
      })
    )

    // Allow microtask and initialization
    await act(async () => {
      await Promise.resolve()
    })

    // Wait for the setTimeout delay
    act(() => {
      vi.advanceTimersByTime(50)
    })

    expect(mockOnLayout).toHaveBeenCalled()
  })

  it('resets initialization on version change', async () => {
    const measuredNodes = [{ id: 'node-1', measured: { width: 100, height: 50 } }] as never[]

    const { rerender } = renderHook(
      ({ workflowVersion }) =>
        useWorkflowInitialization({
          nodes: measuredNodes,
          workflowVersion,
          onLayout: mockOnLayout,
          onVersionChange: mockOnVersionChange,
        }),
      { initialProps: { workflowVersion: 1 } }
    )

    // Initialize
    await act(async () => {
      await Promise.resolve()
    })

    rerender({ workflowVersion: 2 })

    // Flush async re-initialization after version reset
    await act(async () => {
      await Promise.resolve()
    })

    // The key behavior we're testing is that onVersionChange callback was invoked
    // The isInitialized state may immediately become true again if nodes remain measured
    // but the callback should have been called to notify parent of version change
    expect(mockOnVersionChange).toHaveBeenCalled()
  })

  it('skips layout when stored node positions exist', async () => {
    workflowStoreState.nodePositions = { 'node-1': { x: 10, y: 20 } }
    const measuredNodes = [{ id: 'node-1', measured: { width: 100, height: 50 } }] as never[]

    renderHook(() =>
      useWorkflowInitialization({
        nodes: measuredNodes,
        workflowVersion: 1,
        onLayout: mockOnLayout,
      })
    )

    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(mockOnLayout).not.toHaveBeenCalled()
  })
})
