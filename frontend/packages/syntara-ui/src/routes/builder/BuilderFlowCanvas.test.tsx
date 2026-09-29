import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { BuilderFlowCanvas } from './BuilderFlowCanvas'
import type { EdgeType } from './utils/workflowToGraph'

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="reactflow">{children}</div>,
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  ConnectionLineType: { SmoothStep: 'smoothstep' },
}))

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

describe('BuilderFlowCanvas', () => {
  it('renders the React Flow canvas shell', () => {
    render(<BuilderFlowCanvas {...defaultProps} />)

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-controls')).toBeInTheDocument()
    expect(screen.getByTestId('undo-redo')).toBeInTheDocument()
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
