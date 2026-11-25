import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { mergeNodesPreservingPositions, useNodeUpdates } from './useNodeUpdates'

describe('mergeNodesPreservingPositions', () => {
  it('preserves positions from existing nodes', () => {
    const prevNodes = [
      { id: 'node-1', data: { old: true }, position: { x: 100, y: 200 }, measured: { width: 50 } },
    ] as never[]
    const initialNodes = [{ id: 'node-1', data: { new: true } }] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    const node1 = result.find((n) => (n as { id: string }).id === 'node-1')
    expect((node1 as { position: { x: number; y: number } }).position).toEqual({ x: 100, y: 200 })
    expect((node1 as { measured: { width: number } }).measured).toEqual({ width: 50 })
  })

  it('adds new nodes that do not exist in previous list', () => {
    const prevNodes = [{ id: 'node-1', data: {}, position: { x: 0, y: 0 } }] as never[]
    const initialNodes = [
      { id: 'node-1', data: {} },
      { id: 'node-2', data: {}, position: { x: 10, y: 20 } },
    ] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    expect(result).toHaveLength(2)
    const node2 = result.find((n) => (n as { id: string }).id === 'node-2')
    expect(node2).toBeDefined()
    expect((node2 as { position: { x: number; y: number } }).position).toEqual({ x: 10, y: 20 })
  })

  it('applies a stored position to a brand-new node (embedded group placement)', () => {
    const prevNodes = [{ id: 'node-1', data: {}, position: { x: 0, y: 0 } }] as never[]
    const initialNodes = [
      { id: 'node-1', data: {} },
      { id: 'copied', data: {}, position: { x: 0, y: 0 } },
    ] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes, { copied: { x: 640, y: 120 } })

    const copied = result.find((n) => (n as { id: string }).id === 'copied')
    // Without a stored position the node would keep (0,0) and stack; with one it adopts it.
    expect((copied as { position: { x: number; y: number } }).position).toEqual({ x: 640, y: 120 })
  })

  it('preserves non-initial nodes (like placeholder nodes)', () => {
    const prevNodes = [
      { id: 'node-1', data: {}, position: { x: 0, y: 0 } },
      { id: 'placeholder-node-1', type: 'placeholder', position: { x: 100, y: 100 } },
    ] as never[]
    const initialNodes = [{ id: 'node-1', data: { updated: true } }] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    expect(result).toHaveLength(2)
    const placeholder = result.find((n) => (n as { id: string }).id === 'placeholder-node-1')
    expect(placeholder).toBeDefined()
    expect((placeholder as { position: { x: number; y: number } }).position).toEqual({ x: 100, y: 100 })
  })

  it('preserves __validationError flag from existing nodes', () => {
    const prevNodes = [
      {
        id: 'node-1',
        data: { __validationError: true, name: 'A' },
        position: { x: 10, y: 20 },
        measured: { width: 50 },
      },
      { id: 'node-2', data: { name: 'B' }, position: { x: 30, y: 40 }, measured: { width: 50 } },
    ] as never[]
    const initialNodes = [
      { id: 'node-1', data: { name: 'A updated' } },
      { id: 'node-2', data: { name: 'B' } },
    ] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    const node1 = result.find((n) => (n as { id: string }).id === 'node-1')
    const node2 = result.find((n) => (n as { id: string }).id === 'node-2')
    expect((node1 as { data: Record<string, unknown> }).data.__validationError).toBe(true)
    expect((node1 as { data: Record<string, unknown> }).data.name).toBe('A updated')
    expect((node2 as { data: Record<string, unknown> }).data.__validationError).toBeUndefined()
  })

  it('does not add __validationError when existing node does not have it', () => {
    const prevNodes = [{ id: 'node-1', data: { name: 'A' }, position: { x: 10, y: 20 } }] as never[]
    const initialNodes = [{ id: 'node-1', data: { name: 'A updated' } }] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    const node1 = result.find((n) => (n as { id: string }).id === 'node-1')
    expect((node1 as { data: Record<string, unknown> }).data.__validationError).toBeUndefined()
  })

  it('returns initialNodes as-is when prevNodes is empty', () => {
    const prevNodes: never[] = []
    const initialNodes = [
      { id: 'node-1', data: {} },
      { id: 'node-2', data: {} },
    ] as never[]

    const result = mergeNodesPreservingPositions(prevNodes, initialNodes)

    expect(result).toEqual(initialNodes)
  })
})

describe('useNodeUpdates', () => {
  const mockSetNodes = vi.fn()
  const mockSetEdges = vi.fn()
  const mockOnNewNodesAdded = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
    mockSetEdges.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([])
      }
    })
  })

  // --- Initialization ---

  it('exposes previousNodeIdsRef and newlyAddedNodeIdsRef', () => {
    const { result } = renderHook(() =>
      useNodeUpdates({
        initialNodes: [],
        initialEdges: [],
        isInitialized: false,
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        workflowVersion: 1,
      })
    )

    expect(result.current.previousNodeIdsRef).toBeDefined()
    expect(result.current.newlyAddedNodeIdsRef).toBeDefined()
  })

  it('skips setNodes on mount when data has not changed', () => {
    renderHook(() =>
      useNodeUpdates({
        initialNodes: [{ id: 'node-1', data: {} }] as never[],
        initialEdges: [],
        isInitialized: false,
        setNodes: mockSetNodes,
        setEdges: mockSetEdges,
        workflowVersion: 1,
      })
    )

    expect(mockSetNodes).not.toHaveBeenCalled()
  })

  it('sets initial nodes when data arrives while not initialized', () => {
    const loadedNodes = [{ id: 'node-1', data: {} }] as never[]

    const { rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: false,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [] as never[] } }
    )

    rerender({ initialNodes: loadedNodes })

    expect(mockSetNodes).toHaveBeenCalledWith(loadedNodes)
  })

  // --- Adding nodes ---

  it('tracks new nodes when added', () => {
    const { result, rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          onNewNodesAdded: mockOnNewNodesAdded,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [{ id: 'node-1', data: {} }] as never[] } }
    )

    mockOnNewNodesAdded.mockClear()
    result.current.previousNodeIdsRef.current = new Set(['node-1'])

    rerender({
      initialNodes: [
        { id: 'node-1', data: {} },
        { id: 'node-2', data: {} },
      ] as never[],
    })

    expect(result.current.newlyAddedNodeIdsRef.current.has('node-2')).toBe(true)
    expect(mockOnNewNodesAdded).toHaveBeenCalledWith(['node-2'])
  })

  it('skips already tracked new nodes', () => {
    const { result, rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          onNewNodesAdded: mockOnNewNodesAdded,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [{ id: 'node-1', data: {} }] as never[] } }
    )

    result.current.previousNodeIdsRef.current = new Set(['node-1'])
    result.current.newlyAddedNodeIdsRef.current = new Set(['node-2'])
    mockOnNewNodesAdded.mockClear()

    rerender({
      initialNodes: [
        { id: 'node-1', data: {} },
        { id: 'node-2', data: {} },
      ] as never[],
    })

    expect(mockOnNewNodesAdded).not.toHaveBeenCalled()
  })

  it('merges new edges when nodes are added', () => {
    mockSetEdges.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([{ id: 'edge-1' }])
      }
    })

    const { rerender } = renderHook(
      ({ initialNodes, initialEdges }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges,
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      {
        initialProps: {
          initialNodes: [{ id: 'node-1', data: {} }] as never[],
          initialEdges: [{ id: 'edge-1', source: 'node-1', target: 'node-2' }] as never[],
        },
      }
    )

    rerender({
      initialNodes: [
        { id: 'node-1', data: {} },
        { id: 'node-2', data: {} },
      ] as never[],
      initialEdges: [
        { id: 'edge-1', source: 'node-1', target: 'node-2' },
        { id: 'edge-2', source: 'node-2', target: 'node-3' },
      ] as never[],
    })

    expect(mockSetEdges).toHaveBeenCalled()
  })

  // --- Deletion ---

  it('handles node deletion', () => {
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        return updater([
          { id: 'node-1', position: { x: 10, y: 20 } },
          { id: 'node-2', position: { x: 30, y: 40 } },
        ])
      }
    })

    const { rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      {
        initialProps: {
          initialNodes: [
            { id: 'node-1', data: {} },
            { id: 'node-2', data: {} },
          ] as never[],
        },
      }
    )

    rerender({ initialNodes: [{ id: 'node-1', data: {} }] as never[] })

    expect(mockSetNodes).toHaveBeenCalled()
  })

  it('preserves remaining node positions on deletion', () => {
    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater([
          { id: 'node-1', data: {}, position: { x: 10, y: 20 }, measured: { width: 100 } },
          { id: 'node-2', data: {}, position: { x: 30, y: 40 }, measured: { width: 100 } },
        ])
      }
      return capturedNodes
    })

    const { result, rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      {
        initialProps: {
          initialNodes: [
            { id: 'node-1', data: {} },
            { id: 'node-2', data: {} },
          ] as never[],
        },
      }
    )

    result.current.previousNodeIdsRef.current = new Set(['node-1', 'node-2'])

    rerender({ initialNodes: [{ id: 'node-1', data: {} }] as never[] })

    const remainingNode = capturedNodes.find((n) => (n as { id: string }).id === 'node-1')
    expect((remainingNode as { position: { x: number; y: number } }).position).toEqual({ x: 10, y: 20 })
    expect(capturedNodes.find((n) => (n as { id: string }).id === 'node-2')).toBeUndefined()
  })

  it('filters out stale nodes during deletion, keeping only initial and placeholder nodes', () => {
    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater([
          { id: 'node-1', data: {}, position: { x: 10, y: 20 }, measured: { width: 100 }, type: 'task' },
          { id: 'node-2', data: {}, position: { x: 30, y: 40 }, measured: { width: 100 }, type: 'task' },
          { id: 'placeholder-1', data: {}, position: { x: 0, y: 0 }, type: 'placeholder' },
          { id: 'stale-node', data: {}, position: { x: 50, y: 60 }, type: 'task' },
        ])
      }
      return capturedNodes
    })

    const { result, rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      {
        initialProps: {
          initialNodes: [
            { id: 'node-1', data: {} },
            { id: 'node-2', data: {} },
          ] as never[],
        },
      }
    )

    result.current.previousNodeIdsRef.current = new Set(['node-1', 'node-2'])

    rerender({ initialNodes: [{ id: 'node-1', data: {} }] as never[] })

    const ids = capturedNodes.map((n) => (n as { id: string }).id)
    expect(ids).toContain('node-1')
    expect(ids).toContain('placeholder-1')
    expect(ids).not.toContain('stale-node')
    expect(ids).not.toContain('node-2')
  })

  // --- Position preservation ---

  it('preserves existing node positions on data update', () => {
    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater([
          { id: 'node-1', data: { old: true }, position: { x: 100, y: 200 }, measured: { width: 50 } },
        ])
      }
      return capturedNodes
    })

    const { rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [{ id: 'node-1', data: { old: true } }] as never[] } }
    )

    rerender({ initialNodes: [{ id: 'node-1', data: { old: false } }] as never[] })

    const node = capturedNodes.find((n) => (n as { id: string }).id === 'node-1') as {
      position: { x: number; y: number }
    }
    expect(node?.position).toEqual({ x: 100, y: 200 })
  })

  it('preserves positions on data-only changes', () => {
    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater([
          { id: 'node-1', data: { name: 'old' }, position: { x: 50, y: 60 }, measured: { width: 100 } },
        ])
      }
      return capturedNodes
    })

    const { result, rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [{ id: 'node-1', data: { name: 'old' } }] as never[] } }
    )

    result.current.previousNodeIdsRef.current = new Set(['node-1'])

    rerender({ initialNodes: [{ id: 'node-1', data: { name: 'new' } }] as never[] })

    const node = capturedNodes.find((n) => (n as { id: string }).id === 'node-1')
    expect((node as { position: { x: number; y: number } }).position).toEqual({ x: 50, y: 60 })
  })

  it('preserves placeholder nodes not in initialNodes', () => {
    const prevNodes = [
      { id: 'node-1', data: {}, position: { x: 0, y: 0 } },
      { id: 'placeholder-node-1', type: 'placeholder', position: { x: 100, y: 100 } },
    ]
    let capturedNodes: unknown[] = []
    mockSetNodes.mockImplementation((updater: ((items: unknown[]) => unknown[]) | unknown[]) => {
      if (typeof updater === 'function') {
        capturedNodes = updater(prevNodes)
      }
      return capturedNodes
    })

    const { rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes: [{ id: 'node-1', data: { old: true } }] as never[] } }
    )

    rerender({ initialNodes: [{ id: 'node-1', data: { old: false } }] as never[] })

    const placeholder = capturedNodes.find((n) => (n as { id: string }).id === 'placeholder-node-1')
    expect(placeholder).toBeDefined()
  })

  // --- No-op ---

  it('does not update when nothing changed', () => {
    const initialNodes = [{ id: 'node-1', type: 'task', data: { name: 'Test' } }] as never[]

    const { rerender } = renderHook(
      ({ initialNodes }) =>
        useNodeUpdates({
          initialNodes,
          initialEdges: [],
          isInitialized: true,
          setNodes: mockSetNodes,
          setEdges: mockSetEdges,
          workflowVersion: 1,
        }),
      { initialProps: { initialNodes } }
    )

    mockSetNodes.mockClear()

    rerender({ initialNodes })

    expect(mockSetNodes).not.toHaveBeenCalled()
  })
})
