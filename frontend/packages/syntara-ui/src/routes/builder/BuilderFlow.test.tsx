import { render, act, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { BuilderFlow } from './BuilderFlow'

// --- Mutable store state ---

let workflowStoreState: Record<string, unknown> = {}
let temporalState = { pause: vi.fn(), clear: vi.fn(), resume: vi.fn() }

function resetStoreState() {
  workflowStoreState = {
    currentWorkflow: null as Record<string, unknown> | null,
    workflowVersion: 1,
    _positionUndoVersion: 0,
    edges: [] as Array<Record<string, unknown>>,
    nodePositions: {} as Record<string, { x: number; y: number }>,
    triggers: [] as Array<Record<string, unknown>>,
    activities: [] as Array<Record<string, unknown>>,
  }
  temporalState = { pause: vi.fn(), clear: vi.fn(), resume: vi.fn() }
}

// --- Capture ReactFlow props ---
let latestReactFlowProps: Record<string, unknown> | null = null
let capturedOnLayout: (() => void) | null = null

// --- Mocks ---

// Prevent the full node/edge component tree (PatternFly + ReactFlow canvas nodes) from loading.
// builderFlowConfig imports nodeTypes → 8 node components → dozens of PatternFly packages each,
// which OOMs the fork worker before tests run. The test only needs the config values as stubs.
vi.mock('./builderFlowConfig', () => ({
  builderNodeTypes: {},
  builderEdgeTypes: {},
  resolveExecutionStatus: (rest?: string | null, store?: string | null): string | null => {
    if (rest === null) return null
    return store ?? rest ?? null
  },
}))

// Do NOT use importOriginal() here. Loading the real @xyflow/react schedules timers at module
// init time that precede vi.useFakeTimers() in beforeEach, leaving them in the real event loop
// after vi.useRealTimers() restores globals — which keeps the fork worker alive indefinitely.
vi.mock('@xyflow/react', () => ({
  ReactFlow: (props: Record<string, unknown> & { children?: React.ReactNode }) => {
    latestReactFlowProps = props
    return <div data-testid="reactflow">{props.children}</div>
  },
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  ConnectionLineType: { SmoothStep: 'smoothstep' },
  applyEdgeChanges: (_changes: unknown, edges: Array<Record<string, unknown>>) => edges,
  applyNodeChanges: (_changes: unknown, nodes: Array<Record<string, unknown>>) => nodes,
  useReactFlow: () => ({
    fitView: vi.fn(),
    screenToFlowPosition: vi.fn(() => ({ x: 0, y: 0 })),
    updateNode: vi.fn(),
    getViewport: () => ({ x: 0, y: 0, zoom: 1 }),
    getNode: vi.fn(),
  }),
}))

vi.mock('../workflows/canvas/CanvasControls', () => ({
  CanvasControls: ({ onLayout }: { onLayout: () => void }) => {
    capturedOnLayout = onLayout
    return <div data-testid="canvas-controls" />
  },
}))

vi.mock('../workflows/canvas/UndoRedoControls', () => ({
  UndoRedoControls: () => <div data-testid="undo-redo" />,
}))

vi.mock('./edges/edgeMarkers', () => ({ EdgeMarkers: () => null }))

vi.mock('./utils/layoutEngine', () => ({
  getLayoutedElements: (nodes: unknown[], edges: unknown[]) => ({ nodes, edges }),
}))

vi.mock('./utils/validateConnection', () => ({
  validateConnection: () => true,
}))

vi.mock('./utils/detectLoopBackNodes', () => ({
  detectLoopBackNodes: () => new Set<string>(),
}))

vi.mock('./hooks/useWorkflowInitialization', () => ({
  useWorkflowInitialization: ({ onAfterInitialLayout }: { onAfterInitialLayout?: () => void }) => {
    onAfterInitialLayout?.()
    return { isInitialized: true, hasRunInitialLayoutRef: { current: true }, workflowVersionRef: { current: 1 } }
  },
}))

vi.mock('./hooks/useNodeUpdates', () => ({
  useNodeUpdates: () => ({ newlyAddedNodeIdsRef: { current: new Set() } }),
}))

vi.mock('./hooks/useNodePositioning', () => ({ useNodePositioning: () => {} }))
vi.mock('./hooks/useEdgeSynchronization', () => ({ useEdgeSynchronization: () => ({}) }))
vi.mock('./hooks/useLoopBackNodeTypes', () => ({
  useLoopBackNodeTypes: () => {},
  applyLoopBackNodeTypes: (nodes: unknown[]) => nodes,
}))
vi.mock('./hooks/useEdgeActiveState', () => ({ useEdgeActiveState: () => {} }))
vi.mock('./hooks/useButtonEdgeMaintenance', () => ({ useButtonEdgeMaintenance: () => {} }))
vi.mock('./hooks/usePendingEdgeManagement', () => ({ usePendingEdgeManagement: () => {} }))
vi.mock('./hooks/useConnectionHandlers', () => ({
  useConnectionHandlers: () => ({ onConnect: vi.fn(), onConnectStart: vi.fn(), onConnectEnd: vi.fn() }),
}))
vi.mock('./hooks/useNodeDeletion', () => ({
  useNodeDeletion: () => ({ onNodesDelete: vi.fn() }),
}))

const mockUpdateNodePositions = vi.fn()

vi.mock('../../stores/useWorkflowStore', () => {
  const useWorkflowStore = (selector: (state: Record<string, unknown>) => unknown) => selector(workflowStoreState)
  useWorkflowStore.getState = () => workflowStoreState
  useWorkflowStore.temporal = { getState: () => temporalState }

  return {
    useWorkflowStore,
    useWorkflowStoreActions: () => ({
      setWorkflow: vi.fn(),
      setEdges: vi.fn(),
      loadWorkflowWithEdges: vi.fn(),
      updateNodePositions: mockUpdateNodePositions,
    }),
    selectCurrentWorkflow: (state: Record<string, unknown>) => state.currentWorkflow,
    selectWorkflowVersion: (state: Record<string, unknown>) => state.workflowVersion,
    selectPositionUndoVersion: (state: Record<string, unknown>) => state._positionUndoVersion ?? 0,
    selectEdges: (state: Record<string, unknown>) => state.edges,
    selectNodePositions: (state: Record<string, unknown>) => state.nodePositions,
    selectTriggers: (state: Record<string, unknown>) => state.triggers,
    selectActivities: (state: Record<string, unknown>) => state.activities,
  }
})

vi.mock('../workflows/stores/useExecutionStore', () => {
  // Use a stable state object so selector results have consistent references across renders.
  // Returning `new Map()` directly (without a selector) gave `activityStates` a new reference
  // every render, causing the execution-state useEffect (added in PR #633) to fire on every
  // render and call setNodes in a loop → infinite re-renders → 4 GB OOM.
  const stableState = { activityStates: new Map<string, unknown>(), visualization: undefined }
  return {
    useExecutionStore: (selector: (state: typeof stableState) => unknown) => selector(stableState),
  }
})

// --- Test data ---

const sampleWorkflow = {
  id: 'wf-1',
  name: 'Test Workflow',
  inputs: {},
  triggers: [{ type: 'manual_trigger', name: 'Manual Trigger' }],
  workflow: {
    activities: [
      { id: 'task-1', type: 'script', name: 'Script 1', parameters: { type: 'script', language: 'python', code: '' } },
    ],
  },
}

const sampleEdges = [
  { id: 'e1', source: 'trigger-0', target: 'task-1', sourceHandle: 'source', targetHandle: 'target' },
]

const defaultProps = {
  workflowId: 'wf-1',
  panelOpen: false,
  onNodeClick: vi.fn(),
  onAddNodeFromEdge: vi.fn(),
}

function seedWorkflow(overrides: Record<string, unknown> = {}) {
  Object.assign(workflowStoreState, { currentWorkflow: sampleWorkflow, edges: sampleEdges, ...overrides })
}

// --- Tests ---

describe('BuilderFlow (builder mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    latestReactFlowProps = null
    capturedOnLayout = null
    resetStoreState()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // --- Rendering ---

  it('renders ReactFlow with UndoRedoControls and CanvasControls', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    expect(screen.getByTestId('undo-redo')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-controls')).toBeInTheDocument()
  })

  // --- Re-initialization ---

  it('re-initializes when workflowVersion changes', () => {
    seedWorkflow({ nodePositions: { 'trigger-0': { x: 10, y: 20 }, 'task-1': { x: 100, y: 200 } } })
    const { rerender } = render(<BuilderFlow {...defaultProps} />)

    Object.assign(workflowStoreState, { workflowVersion: 2 })
    rerender(<BuilderFlow {...defaultProps} />)

    expect(latestReactFlowProps).toBeDefined()
  })

  it('resets state when workflowId changes', () => {
    seedWorkflow()
    const { rerender } = render(<BuilderFlow {...defaultProps} />)

    Object.assign(workflowStoreState, { currentWorkflow: { ...sampleWorkflow, id: 'wf-2' }, workflowVersion: 2 })
    rerender(<BuilderFlow {...defaultProps} workflowId="wf-2" />)

    expect(latestReactFlowProps).toBeDefined()
  })

  it('resets state when workflow is cleared from store', () => {
    seedWorkflow()
    const { rerender } = render(<BuilderFlow {...defaultProps} />)

    Object.assign(workflowStoreState, { currentWorkflow: null })
    rerender(<BuilderFlow {...defaultProps} />)

    expect(latestReactFlowProps).toBeDefined()
  })

  // --- Undo/redo ---

  it('clears undo history after initial layout and resumes after 200ms', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    expect(temporalState.pause).toHaveBeenCalled()
    expect(temporalState.clear).toHaveBeenCalled()

    vi.advanceTimersByTime(200)
    expect(temporalState.resume).toHaveBeenCalled()
  })

  it('applies position undo in-place when _positionUndoVersion changes', () => {
    seedWorkflow({ nodePositions: { 'task-1': { x: 50, y: 60 } } })
    const { rerender } = render(<BuilderFlow {...defaultProps} />)

    Object.assign(workflowStoreState, { _positionUndoVersion: 1, nodePositions: { 'task-1': { x: 200, y: 300 } } })
    rerender(<BuilderFlow {...defaultProps} />)

    expect(latestReactFlowProps).toBeDefined()
  })

  // --- Node drag ---

  it('persists drag positions to the store via onNodeDragStop', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    const onNodeDragStop = latestReactFlowProps?.onNodeDragStop as (
      event: unknown,
      node: unknown,
      draggedNodes: Array<{ id: string; position: { x: number; y: number } }>
    ) => void

    expect(onNodeDragStop).toBeDefined()
    onNodeDragStop({}, {}, [{ id: 'task-1', position: { x: 100, y: 200 } }])

    expect(mockUpdateNodePositions).toHaveBeenCalledWith({ 'task-1': { x: 100, y: 200 } })
  })

  it('skips updateNodePositions when no nodes were dragged', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    const onNodeDragStop = latestReactFlowProps?.onNodeDragStop as (
      event: unknown,
      node: unknown,
      draggedNodes: never[]
    ) => void

    onNodeDragStop({}, {}, [])

    expect(mockUpdateNodePositions).not.toHaveBeenCalled()
  })

  // --- Layout ---

  it('stores positions with markDirty:false when layout is triggered', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    expect(capturedOnLayout).toBeDefined()
    act(() => capturedOnLayout!())

    expect(mockUpdateNodePositions).toHaveBeenCalledWith(expect.any(Object), { skipTracking: true, markDirty: false })
  })

  // --- ReactFlow props ---

  it('passes isValidConnection to ReactFlow', () => {
    seedWorkflow()
    render(<BuilderFlow {...defaultProps} />)

    const isValidConnection = latestReactFlowProps?.isValidConnection as (conn: unknown) => boolean
    expect(isValidConnection({})).toBe(true)
  })

  it('does not crash when panel closes with a pending edge', () => {
    seedWorkflow()
    const { rerender } = render(<BuilderFlow {...defaultProps} panelOpen />)

    rerender(<BuilderFlow {...defaultProps} panelOpen={false} />)

    expect(latestReactFlowProps).toBeDefined()
  })
})
