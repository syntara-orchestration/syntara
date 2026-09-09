import { act, renderHook } from '@testing-library/react'
import { MarkerType } from '@xyflow/react'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useEdgeHandlers } from './useEdgeHandlers'

// Mock dependencies
const mockSetEdges = vi.fn()
const mockGetEdge = vi.fn()

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useReactFlow: () => ({
      setEdges: mockSetEdges,
      getEdge: mockGetEdge,
    }),
  }
})

vi.mock('./useEdgeHover', () => ({
  useEdgeHover: () => ({
    isHovered: false,
    isEdgeHovered: false,
    handleEdgeMouseEnter: vi.fn(),
    handleEdgeMouseLeave: vi.fn(),
    handleButtonMouseEnter: vi.fn(),
    handleButtonMouseLeave: vi.fn(),
  }),
  useEdgeSourceHandle: () => 'source-handle',
}))

describe('useEdgeHandlers', () => {
  const defaultProps = {
    edgeId: 'edge-1',
    source: 'node-1',
    target: 'node-2',
    markerEnd: 'url(#arrow)',
    selected: false,
    data: undefined,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetEdge.mockReturnValue({ sourceHandle: 'handle-1' })
  })

  it('returns hover state handlers', () => {
    const { result } = renderHook(() => useEdgeHandlers(defaultProps))

    expect(result.current.handleEdgeMouseEnter).toBeDefined()
    expect(result.current.handleEdgeMouseLeave).toBeDefined()
    expect(result.current.handleButtonMouseEnter).toBeDefined()
    expect(result.current.handleButtonMouseLeave).toBeDefined()
  })

  it('returns effectiveMarkerEnd based on state', () => {
    const { result } = renderHook(() => useEdgeHandlers(defaultProps))

    // Default state (not selected, not hovered, not active)
    expect(result.current.effectiveMarkerEnd).toBe('url(#arrow)')
  })

  it('returns selected marker when selected', () => {
    const { result } = renderHook(() => useEdgeHandlers({ ...defaultProps, selected: true }))

    expect(result.current.effectiveMarkerEnd).toBe("url('#selected-arrow-marker')")
  })

  it('handleDelete removes edge from edges array', () => {
    const { result } = renderHook(() => useEdgeHandlers(defaultProps))

    const mockStopPropagation = vi.fn()
    const mockEvent = { stopPropagation: mockStopPropagation } as unknown as React.MouseEvent

    act(() => {
      result.current.handleDelete(mockEvent)
    })

    expect(mockStopPropagation).toHaveBeenCalled()
    expect(mockSetEdges).toHaveBeenCalled()

    // Test the filter function
    const filterFn = mockSetEdges.mock.calls[0][0] as (edges: { id: string }[]) => { id: string }[]
    const edges = [{ id: 'edge-1' }, { id: 'edge-2' }]
    const filtered = filterFn(edges)
    expect(filtered).toEqual([{ id: 'edge-2' }])
  })

  it('handleAddNode calls data.onAddNode when defined', () => {
    const mockOnAddNode = vi.fn()
    const props = {
      ...defaultProps,
      data: { onAddNode: mockOnAddNode },
    }

    const { result } = renderHook(() => useEdgeHandlers(props))

    const mockStopPropagation = vi.fn()
    const mockEvent = { stopPropagation: mockStopPropagation } as unknown as React.MouseEvent

    act(() => {
      result.current.handleAddNode(mockEvent)
    })

    expect(mockStopPropagation).toHaveBeenCalled()
    expect(mockOnAddNode).toHaveBeenCalledWith({
      sourceNodeId: 'node-1',
      targetNodeId: 'node-2',
      edgeId: 'edge-1',
      sourceHandle: 'source-handle',
    })
  })

  it('handleAddNode does nothing when data.onAddNode is not defined', () => {
    const { result } = renderHook(() => useEdgeHandlers(defaultProps))

    const mockStopPropagation = vi.fn()
    const mockEvent = { stopPropagation: mockStopPropagation } as unknown as React.MouseEvent

    act(() => {
      result.current.handleAddNode(mockEvent)
    })

    expect(mockStopPropagation).toHaveBeenCalled()
    // Should not throw
  })

  it('handles markerEnd as object by returning undefined', () => {
    const props = {
      ...defaultProps,
      markerEnd: { type: MarkerType.Arrow, width: 10, height: 10, color: 'red' },
    }

    const { result } = renderHook(() => useEdgeHandlers(props))

    // When markerEnd is object and not selected/hovered, should return undefined
    expect(result.current.effectiveMarkerEnd).toBeUndefined()
  })
})
