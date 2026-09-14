import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import type { FlowPosition } from '../types'

import { useNodePositioning } from './useNodePositioning'

describe('useNodePositioning', () => {
  const mockSetNodes = vi.fn()
  const mockGetViewport = vi.fn(() => ({ x: 0, y: 0, zoom: 1 }))
  const mockUpdateNode = vi.fn()
  const mockContainerRef = { current: { clientWidth: 1000 } as HTMLDivElement }
  const newlyAddedNodeIdsRef = { current: new Set<string>() }

  const mockUpdateNodePositions = vi.fn()

  const defaultParams = {
    nodes: [] as never[],
    edges: [] as never[],
    isInitialized: true,
    newlyAddedNodeIdsRef,
    containerRef: mockContainerRef,
    setNodes: mockSetNodes,
    getViewport: mockGetViewport,
    updateNode: mockUpdateNode,
    updateNodePositions: mockUpdateNodePositions,
    desiredPosition: null as FlowPosition | null,
    onClearDesiredPosition: undefined,
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    newlyAddedNodeIdsRef.current = new Set()
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does nothing when no newly added nodes', () => {
    renderHook(() => useNodePositioning(defaultParams))

    expect(mockSetNodes).not.toHaveBeenCalled()
  })

  it('does nothing when not initialized', () => {
    newlyAddedNodeIdsRef.current.add('node-1')

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        isInitialized: false,
      })
    )

    expect(mockSetNodes).not.toHaveBeenCalled()
  })

  it('positions regular nodes on right side of viewport', () => {
    const nodes = [
      { id: 'node-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')

    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
    const positionedNode = capturedNodes.find((n) => (n as { id: string }).id === 'node-1') as {
      position: { x: number; y: number }
    }
    expect(positionedNode?.position.x).toBeGreaterThan(0)
  })

  it('positions loop nodes on left side of viewport', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop', position: { x: 0, y: 0 }, measured: { width: 240, height: 100 } },
      { id: 'body-1', type: 'task', position: { x: 340, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' }] as never[]

    newlyAddedNodeIdsRef.current.add('loop-1')
    newlyAddedNodeIdsRef.current.add('body-1')

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
  })

  it('positions first loop node at desiredPosition and clears it (hasLoopBodyNodes path)', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop', position: { x: 0, y: 0 }, measured: { width: 240, height: 100 } },
      { id: 'body-1', type: 'task', position: { x: 340, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' }] as never[]
    newlyAddedNodeIdsRef.current.add('loop-1')
    newlyAddedNodeIdsRef.current.add('body-1')
    const desiredPosition = { x: 200, y: 150 }
    const mockOnClear = vi.fn()

    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
        desiredPosition,
        onClearDesiredPosition: mockOnClear,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
    const positionedLoop = capturedNodes.find((n) => (n as { id: string }).id === 'loop-1') as {
      position: { x: number; y: number }
    }
    // Loop height 100 → center at y+50; center at 150 so top-left y = 100
    expect(positionedLoop?.position).toEqual({ x: 200, y: 100 })
    vi.runAllTimers()
    expect(mockOnClear).toHaveBeenCalled()
  })

  it('removes node from tracking after positioning', () => {
    const nodes = [
      { id: 'node-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
      })
    )

    vi.runAllTimers()
    expect(newlyAddedNodeIdsRef.current.has('node-1')).toBe(false)
  })

  it('skips nodes that are not measured', () => {
    const nodes = [{ id: 'node-1', type: 'task', position: { x: 0, y: 0 } }] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
      })
    )

    // Should not be processed (no measured property)
    vi.runAllTimers()
    expect(newlyAddedNodeIdsRef.current.has('node-1')).toBe(true)
  })

  it('skips nodes that already have position', () => {
    const nodes = [
      { id: 'node-1', type: 'task', position: { x: 100, y: 100 }, measured: { width: 100, height: 50 } },
    ] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
      })
    )

    // Should not be processed (already has position)
    vi.runAllTimers()
    expect(newlyAddedNodeIdsRef.current.has('node-1')).toBe(true)
  })

  it('positions new node so its center aligns with desiredPosition (handle at edge end)', () => {
    const nodes = [
      { id: 'node-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')
    const desiredPosition = { x: 200, y: 150 }
    const mockOnClear = vi.fn()

    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        desiredPosition,
        onClearDesiredPosition: mockOnClear,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
    const positionedNode = capturedNodes.find((n) => (n as { id: string }).id === 'node-1') as {
      position: { x: number; y: number }
    }
    // Node height 50 → center at y+25; we want center at 150 so top-left y = 125
    expect(positionedNode?.position).toEqual({ x: 200, y: 125 })
    vi.runAllTimers()
    expect(mockOnClear).toHaveBeenCalled()
  })

  it('uses window.innerWidth when container is not available', () => {
    const nodes = [
      { id: 'node-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    newlyAddedNodeIdsRef.current.add('node-1')

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        containerRef: { current: null },
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
  })

  it('calls updateNode for positioned loop nodes after timeout', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop', position: { x: 0, y: 0 }, measured: { width: 240, height: 100 } },
      { id: 'body-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' }] as never[]

    newlyAddedNodeIdsRef.current.add('loop-1')
    newlyAddedNodeIdsRef.current.add('body-1')

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
      })
    )

    // Fast-forward the 100ms timeout
    vi.advanceTimersByTime(100)

    // updateNode should have been called for positioned nodes
    expect(mockUpdateNode).toHaveBeenCalled()
  })

  it('positions loop body node relative to loop node', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop', position: { x: 0, y: 0 }, measured: { width: 240, height: 100 } },
      { id: 'body-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' }] as never[]

    newlyAddedNodeIdsRef.current.add('loop-1')
    newlyAddedNodeIdsRef.current.add('body-1')

    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
    const positionedBody = capturedNodes.find((n) => (n as { id: string }).id === 'body-1') as {
      position: { x: number; y: number }
    }
    // Body node positioned using unified spacing constants
    // Loop is positioned at baseX=50, baseY=50, width=240, so body is at 50+240+80=370, 50+100=150
    expect(positionedBody?.position.x).toBe(370) // 50 (loop.x) + 240 (loop.width) + 80 (LOOP_BODY_SPACING.horizontal)
    expect(positionedBody?.position.y).toBe(150) // 50 (loop.y) + 100 (LOOP_BODY_SPACING.vertical)
  })

  it('does not position loop body node if loop position is not found', () => {
    const nodes = [
      { id: 'body-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-missing', target: 'body-1', sourceHandle: 'loop' }] as never[]

    newlyAddedNodeIdsRef.current.add('body-1')

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
      })
    )

    // Body node should not be positioned if loop is not found
    vi.runAllTimers()
    expect(newlyAddedNodeIdsRef.current.has('body-1')).toBe(true)
  })

  it('clears desiredPosition only in loop branch', () => {
    const nodes = [
      { id: 'loop-1', type: 'loop', position: { x: 0, y: 0 }, measured: { width: 240, height: 100 } },
      { id: 'body-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop' }] as never[]
    newlyAddedNodeIdsRef.current.add('loop-1')
    newlyAddedNodeIdsRef.current.add('body-1')
    const desiredPosition = { x: 200, y: 150 }
    const mockOnClear = vi.fn()

    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
        desiredPosition,
        onClearDesiredPosition: mockOnClear,
      })
    )

    // Should clear desiredPosition even if not used for first loop
    vi.runAllTimers()
    expect(mockOnClear).toHaveBeenCalled()
  })

  it('positions non-loop body nodes without loop body map', () => {
    const nodes = [
      { id: 'task-1', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
      { id: 'task-2', type: 'task', position: { x: 0, y: 0 }, measured: { width: 100, height: 50 } },
    ] as never[]
    const edges = [{ id: 'e1', source: 'task-1', target: 'task-2', sourceHandle: 'source' }] as never[]

    newlyAddedNodeIdsRef.current.add('task-1')
    newlyAddedNodeIdsRef.current.add('task-2')

    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(nodes)
      }
    })

    renderHook(() =>
      useNodePositioning({
        ...defaultParams,
        nodes,
        edges,
      })
    )

    vi.runAllTimers()
    expect(mockSetNodes).toHaveBeenCalled()
    // Both nodes should be positioned
    expect(capturedNodes.length).toBe(2)
  })
})
