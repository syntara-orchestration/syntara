import { render, screen } from '@testing-library/react'
import { Position } from '@xyflow/react'
import type React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoopBackEdge } from './LoopBackEdge'

const mockNodesConnectable = vi.hoisted(() => ({ value: true }))
const mockIsHovered = vi.hoisted(() => ({ value: false }))

// Mock @xyflow/react
const mockGetNodes = vi.fn()
vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useReactFlow: () => ({
      getNodes: mockGetNodes,
    }),
    useStore: (selector: (s: { nodesConnectable: boolean }) => boolean) =>
      selector({ nodesConnectable: mockNodesConnectable.value }),
  }
})

// Mock sub-components
vi.mock('./EdgePath', () => ({
  EdgePath: ({ edgePath }: { edgePath: string }) => <path data-testid="edge-path" d={edgePath} />,
}))

vi.mock('./EdgeLabel', () => ({
  EdgeLabel: ({ label }: { label?: React.ReactNode }) => (label ? <span data-testid="edge-label">{label}</span> : null),
}))

vi.mock('./EdgeActions', () => ({
  EdgeActions: () => <div data-testid="edge-actions" />,
}))

vi.mock('./useEdgeHandlers', () => ({
  useEdgeHandlers: () => ({
    isHovered: mockIsHovered.value,
    isEdgeHovered: false,
    effectiveMarkerEnd: 'url(#arrow)',
    handleEdgeMouseEnter: vi.fn(),
    handleEdgeMouseLeave: vi.fn(),
    handleButtonMouseEnter: vi.fn(),
    handleButtonMouseLeave: vi.fn(),
    handleDelete: vi.fn(),
    handleAddNode: vi.fn(),
  }),
}))

vi.mock('./edgeUtils', () => ({
  adjustSourceCoordinates: (x: number, y: number) => ({ x, y }),
}))

describe('LoopBackEdge', () => {
  const defaultProps = {
    id: 'edge-1',
    source: 'body-node',
    target: 'loop-node',
    sourceX: 300,
    sourceY: 150,
    targetX: 100,
    targetY: 50,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }

  beforeEach(() => {
    mockGetNodes.mockReturnValue([
      { id: 'loop-node', position: { x: 50, y: 25 }, measured: { height: 50 } },
      { id: 'body-node', position: { x: 250, y: 125 }, measured: { height: 50 } },
    ])
  })

  it('renders EdgePath', () => {
    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.getByTestId('edge-path')).toBeInTheDocument()
  })

  it('does not render EdgeLabel when no label', () => {
    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.queryByTestId('edge-label')).not.toBeInTheDocument()
  })

  it('renders EdgeLabel when label is provided', () => {
    render(<LoopBackEdge {...defaultProps} label="Back" />)
    expect(screen.getByTestId('edge-label')).toBeInTheDocument()
  })

  it('does not show EdgeActions when not hovered', () => {
    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
  })

  it('calculates path around loop body nodes', () => {
    // Add an intermediate node
    mockGetNodes.mockReturnValue([
      { id: 'loop-node', position: { x: 50, y: 25 }, measured: { height: 50 } },
      { id: 'body-node', position: { x: 250, y: 125 }, measured: { height: 50 } },
      { id: 'middle-node', position: { x: 150, y: 25 }, measured: { height: 100 } },
    ])

    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.getByTestId('edge-path')).toBeInTheDocument()
  })

  it('handles nodes without measured dimensions', () => {
    mockGetNodes.mockReturnValue([
      { id: 'loop-node', position: { x: 50, y: 25 } },
      { id: 'body-node', position: { x: 250, y: 125 } },
    ])

    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.getByTestId('edge-path')).toBeInTheDocument()
  })

  it('shows EdgeActions when data.isActive is true', () => {
    render(<LoopBackEdge {...defaultProps} data={{ isActive: true }} />)
    expect(screen.getByTestId('edge-actions')).toBeInTheDocument()
  })

  it('shows EdgeActions when hovered', () => {
    mockIsHovered.value = true
    render(<LoopBackEdge {...defaultProps} />)
    expect(screen.getByTestId('edge-actions')).toBeInTheDocument()
    mockIsHovered.value = false
  })

  it('hides EdgeActions when hovered but isPending', () => {
    mockIsHovered.value = true
    render(<LoopBackEdge {...defaultProps} data={{ isPending: true }} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
    mockIsHovered.value = false
  })

  it('hides EdgeActions when hovered but has executionStatus', () => {
    mockIsHovered.value = true
    render(<LoopBackEdge {...defaultProps} data={{ executionStatus: 'pending' }} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
    mockIsHovered.value = false
  })

  it('hides EdgeActions when isPending is true', () => {
    render(<LoopBackEdge {...defaultProps} data={{ isActive: true, isPending: true }} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
  })

  it('hides EdgeActions when executionStatus is set', () => {
    render(<LoopBackEdge {...defaultProps} data={{ isActive: true, executionStatus: 'passed' }} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
  })

  it('hides edge actions when nodesConnectable is false', () => {
    mockNodesConnectable.value = false
    render(<LoopBackEdge {...defaultProps} data={{ isActive: true }} />)
    expect(screen.queryByTestId('edge-actions')).not.toBeInTheDocument()
    mockNodesConnectable.value = true
  })
})
