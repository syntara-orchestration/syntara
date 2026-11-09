import { act, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FlowNodeType } from '../../constants'
import { type ButtonEdgePlaceholderNode, type NodeType } from '../workflows/canvas/nodes/NodeType'

import { BuilderFlowCanvas } from './BuilderFlowCanvas'
import { RETRY_LABEL_BASE_OFFSET, RETRY_LABEL_HEIGHT, RETRY_LABEL_LANE_GAP } from './retryPreviewLabelLayout'
import type { EdgeType } from './utils/workflowToGraph'

let latestReactFlowProps: Record<string, unknown> | null = null

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
    ReactFlow: (props: Record<string, unknown> & { children?: ReactNode }) => {
      latestReactFlowProps = props
      return <div data-testid="reactflow">{props.children}</div>
    },
    NodeToolbar: ({
      children,
      'data-testid': testId,
      position,
      align,
      offset,
    }: {
      children?: ReactNode
      'data-testid'?: string
      position?: string
      align?: string
      offset?: number
    }) => (
      <div data-testid={testId} data-position={position} data-align={align} data-offset={offset}>
        {children}
      </div>
    ),
    Background: () => null,
    BackgroundVariant: { Dots: 'dots' },
    ConnectionLineType: { SmoothStep: 'smoothstep' },
    Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
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
const placeholderNode: ButtonEdgePlaceholderNode = {
  id: 'placeholder-1',
  type: FlowNodeType.PLACEHOLDER,
  position: { x: 50, y: 0 },
  data: {},
}
const nodesWithPlaceholder = [...nodes, placeholderNode]
const placeholderOnlyNodes = [placeholderNode]
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
    latestReactFlowProps = null
  })

  it('renders the React Flow canvas shell', () => {
    render(<BuilderFlowCanvas {...defaultProps} />)

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-controls')).toBeInTheDocument()
    expect(screen.getByTestId('undo-redo')).toBeInTheDocument()
  })

  it('shows retry path labels and highlights the retry origin', () => {
    const retryNodes = [
      {
        id: 'trigger-0',
        type: FlowNodeType.TRIGGER,
        position: { x: 0, y: 0 },
        data: { name: 'Trigger', __executionState: { status: 'completed' } },
      },
      {
        id: 'retry-origin',
        type: FlowNodeType.TASK,
        position: { x: 100, y: 0 },
        data: { name: 'Call API', __executionState: { status: 'failed' } },
      },
      {
        id: 'downstream',
        type: FlowNodeType.TASK,
        position: { x: 200, y: 0 },
        data: { name: 'Publish', __executionState: { status: 'skipped' } },
      },
      {
        id: 'retained',
        type: FlowNodeType.TASK,
        position: { x: 100, y: 100 },
        data: { name: 'Retained', __executionState: { status: 'completed' } },
      },
      {
        id: 'unselected-failure',
        type: FlowNodeType.TASK,
        position: { x: 200, y: 100 },
        data: { name: 'Other failure', __executionState: { status: 'failed' } },
      },
    ] as unknown as NodeType[]
    const retryEdges = [
      { id: 'edge-1', source: 'retry-origin', target: 'downstream' },
      { id: 'edge-2', source: 'trigger-0', target: 'retry-origin' },
    ] as EdgeType[]

    render(
      <BuilderFlowCanvas
        {...defaultProps}
        nodes={retryNodes}
        edges={retryEdges}
        retryPreviewNodeIds={['retry-origin']}
      />
    )

    expect(screen.getByTestId('retry-origin-label-retry-origin')).toHaveTextContent('Retry origin')
    expect(screen.getByTestId('retry-state-label-downstream')).toHaveTextContent('In retry scope')
    expect(screen.getByTestId('retry-state-label-retained')).toHaveTextContent('Retains prior result')
    expect(screen.getByTestId('retry-state-label-unselected-failure')).toHaveTextContent('Not retried — remains failed')
    const retryLabels = [
      screen.getByTestId('retry-origin-retry-origin'),
      screen.getByTestId('retry-state-downstream'),
      screen.getByTestId('retry-state-retained'),
      screen.getByTestId('retry-state-unselected-failure'),
    ]
    expect(
      retryLabels.every((label) => ['top', 'left', 'right'].includes(label.getAttribute('data-position') ?? ''))
    ).toBe(true)
    expect(
      retryLabels.every(
        (label) =>
          Number(label.getAttribute('data-offset')) <=
          RETRY_LABEL_BASE_OFFSET + RETRY_LABEL_HEIGHT + RETRY_LABEL_LANE_GAP
      )
    ).toBe(true)
    const renderedNodes = (
      latestReactFlowProps as {
        nodes: Array<{ id: string; data: Record<string, unknown>; ariaLabel?: string }>
      }
    ).nodes
    const originNode = renderedNodes.find((node) => node.id === 'retry-origin')
    expect(originNode?.data.__retryPreviewOrigin).toBe(true)
    expect(originNode?.ariaLabel).toContain('retry origin')
    expect(renderedNodes.find((node) => node.id === 'trigger-0')?.ariaLabel ?? '').not.toContain('retains prior result')
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

  it('excludes placeholder nodes from the batched internals update', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: nodesWithPlaceholder }

    render(<BuilderFlowCanvas {...defaultProps} nodes={nodesWithPlaceholder} />)

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
    expect(flowStore.updateNodeInternals).toHaveBeenCalledWith(['task-1'])
  })

  it('does not update internals when the canvas has only placeholder nodes', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: placeholderOnlyNodes }

    render(<BuilderFlowCanvas {...defaultProps} nodes={placeholderOnlyNodes} />)

    expect(flowStore.updateNodeInternals).not.toHaveBeenCalled()
  })

  it('does not update internals again when only measured dimensions change', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)
    const measuredNodes = multipleNodes.map((node) => ({ ...node, measured: { width: 200, height: 100 } }))

    act(() => updateFlowStore({ nodes: measuredNodes }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
  })

  it('does not update internals when zooming stays above the semantic zoom threshold', () => {
    flowStore.state = { transform: [0, 0, 0.75], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)

    act(() => updateFlowStore({ transform: [0, 0, 0.7] }))

    expect(flowStore.updateNodeInternals).not.toHaveBeenCalled()
  })

  it('does not update internals again when zooming stays within semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)

    act(() => updateFlowStore({ transform: [0, 0, 0.4] }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
  })

  it('updates internals once when a node is added during semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes }
    render(<BuilderFlowCanvas {...defaultProps} />)

    act(() => updateFlowStore({ nodes: multipleNodes }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledTimes(2)
    expect(flowStore.updateNodeInternals).toHaveBeenLastCalledWith(['task-1', 'task-2'])
  })

  it('does not update internals again when a placeholder is added during semantic zoom', () => {
    flowStore.state = { transform: [0, 0, 0.5], nodes: multipleNodes }
    render(<BuilderFlowCanvas {...defaultProps} nodes={multipleNodes} />)

    act(() => updateFlowStore({ nodes: [...multipleNodes, placeholderNode] }))

    expect(flowStore.updateNodeInternals).toHaveBeenCalledOnce()
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
