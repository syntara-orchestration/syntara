import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { BuilderFlowCanvas } from './BuilderFlowCanvas'
import type { EdgeType } from './utils/workflowToGraph'

const flowStore = vi.hoisted(() => ({
  state: {
    transform: [0, 0, 1] as [number, number, number],
    nodes: [] as NodeType[],
  },
  listeners: new Set<() => void>(),
  updateNodeInternals: vi.fn(),
}))

vi.mock('@xyflow/react', async () => {
  const { useRef, useSyncExternalStore } = await import('react')
  return {
    ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="reactflow">{children}</div>,
    Background: () => null,
    BackgroundVariant: { Dots: 'dots' },
    ConnectionLineType: { SmoothStep: 'smoothstep' },
    useStore: (
      selector: (state: typeof flowStore.state) => unknown,
      equalityFn?: (previous: unknown, next: unknown) => boolean
    ) => {
      const state = useSyncExternalStore(
        (listener) => {
          flowStore.listeners.add(listener)
          return () => {
            flowStore.listeners.delete(listener)
          }
        },
        () => flowStore.state
      )
      const selectedRef = useRef<unknown>(undefined)
      const next = selector(state)
      if (selectedRef.current !== undefined && equalityFn?.(selectedRef.current, next)) {
        return selectedRef.current
      }
      selectedRef.current = next
      return next
    },
    useUpdateNodeInternals: () => flowStore.updateNodeInternals,
  }
})

vi.mock('../workflows/canvas/CanvasControls', () => ({
  CanvasControls: () => <div data-testid="canvas-controls" />,
}))

vi.mock('../workflows/canvas/UndoRedoControls', () => ({
  UndoRedoControls: () => <div data-testid="undo-redo" />,
}))

vi.mock('./edges/edgeMarkers', () => ({ EdgeMarkers: () => null }))

vi.mock('./builderFlowConfig', () => ({
  builderNodeTypes: {},
  builderEdgeTypes: {},
}))

const nodes = [{ id: 'task-1', position: { x: 0, y: 0 }, data: {} }] as NodeType[]
const multipleNodes = [...nodes, { id: 'task-2', position: { x: 100, y: 0 }, data: {} }] as NodeType[]
const edges = [{ id: 'e1', source: 'trigger-0', target: 'task-1' }] as EdgeType[]

const defaultProps = {
  containerRef: { current: null },
  effectiveExecutionStatus: null,
  isReadOnly: false,
  nodes,
  edges,
  onNodesChange: vi.fn(),
  onEdgesChange: vi.fn(),
  isValidConnection: () => true,
  onLayout: vi.fn(),
}

function updateFlowStore(partial: Partial<typeof flowStore.state>) {
  flowStore.state = { ...flowStore.state, ...partial }
  flowStore.listeners.forEach((listener) => {
    listener()
  })
}

describe('BuilderFlowCanvas', () => {
  beforeEach(() => {
    flowStore.state = { transform: [0, 0, 1], nodes }
    flowStore.listeners.clear()
    flowStore.updateNodeInternals.mockClear()
  })

  it('renders the React Flow canvas shell', () => {
    render(<BuilderFlowCanvas {...defaultProps} />)

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-controls')).toBeInTheDocument()
    expect(screen.getByTestId('undo-redo')).toBeInTheDocument()
  })

  it('does not update node internals when initially above the semantic zoom threshold', () => {
    render(<BuilderFlowCanvas {...defaultProps} />)

    expect(flowStore.updateNodeInternals).not.toHaveBeenCalled()
  })

  it('updates all node internals in one batch when initially at semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: multipleNodes }

    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
    expect(flowStore.updateNodeInternals).toHaveBeenCalledWith(['task-1', 'task-2'])
  })

  it('batches node internals updates when crossing in and out of semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.75], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)

    act(() => updateFlowStore({ transform: [0, 0, 0.5] }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
    expect(flowStore.updateNodeInternals).toHaveBeenLastCalledWith(['task-1', 'task-2'])

    act(() => updateFlowStore({ transform: [0, 0, 0.75] }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledTimes(2)
    expect(flowStore.updateNodeInternals).toHaveBeenLastCalledWith(['task-1', 'task-2'])
  })

  it('does not update internals again when only measured dimensions change', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)
    const measuredNodes = multipleNodes.map((node) => ({ ...node, measured: { width: 200, height: 100 } }))

    act(() => updateFlowStore({ nodes: measuredNodes }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
  })

  it('updates internals once when a node is added during semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes }
    render(<BuilderFlowCanvas {...defaultProps} />)

    act(() => updateFlowStore({ nodes: multipleNodes }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledTimes(2)
    expect(flowStore.updateNodeInternals).toHaveBeenLastCalledWith(['task-1', 'task-2'])
  })

  it('shows the execution spinner when status is running', () => {
    render(<BuilderFlowCanvas {...defaultProps} effectiveExecutionStatus="running" />)

    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('has no accessibility violations in edit mode', async () => {
    const { container } = render(<BuilderFlowCanvas {...defaultProps} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations while execution is running', async () => {
    const { container } = render(<BuilderFlowCanvas {...defaultProps} effectiveExecutionStatus="running" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
