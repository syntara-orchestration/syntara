import type { TaskActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../../constants'

import { TaskReversedStepComponent } from './TaskReversedNode'

vi.mock('./hooks/useCredentialName', () => ({
  useCredentialName: () => ({ name: undefined, isPending: false }),
}))

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('TaskReversedStepComponent', () => {
  const baseTaskNode = {
    type: 'script',
    id: 'task-reversed-1',
    name: 'Loop Back Task',
    parameters: {
      language: 'python',
      code: 'print("hello")',
    },
  } as TaskActivity

  const createNodeProps = (data: TaskActivity) => ({
    id: data.id,
    data,
    type: FlowNodeType.TASK_REVERSED,
    position: { x: 0, y: 0 },
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    selected: false,
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  })

  describe('Rendering', () => {
    it('renders task reversed node with name', () => {
      render(<TaskReversedStepComponent {...createNodeProps(baseTaskNode)} />)

      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })

    it('renders executor type label', () => {
      render(<TaskReversedStepComponent {...createNodeProps(baseTaskNode)} />)

      // Script executor label
      expect(screen.getByText('Script')).toBeInTheDocument()
    })
  })

  describe('Different Executors', () => {
    it('renders agentic executor', () => {
      const agenticTask = {
        type: 'agentic',
        id: 'task-reversed-2',
        name: 'AI Task',
        parameters: {
          prompt: 'Do something smart',
          model: 'claude-3-sonnet',
        },
      } as TaskActivity

      render(<TaskReversedStepComponent {...createNodeProps(agenticTask)} />)

      expect(screen.getByText('AI Task')).toBeInTheDocument()
      expect(screen.getByText('Task Agent')).toBeInTheDocument()
    })

    it('renders http_request executor', () => {
      const httpTask = {
        type: 'http_request',
        id: 'task-reversed-3',
        name: 'API Call',
        parameters: {
          url: 'https://example.com',
          method: 'GET',
        },
      } as TaskActivity

      render(<TaskReversedStepComponent {...createNodeProps(httpTask)} />)

      expect(screen.getByText('API Call')).toBeInTheDocument()
    })
  })

  describe('Execution State', () => {
    it('handles execution state data', () => {
      const nodeWithExecution = {
        ...baseTaskNode,
        __executionState: {
          status: 'running',
          started_at: '2024-01-01T00:00:00Z',
        },
      } as TaskActivity

      render(<TaskReversedStepComponent {...createNodeProps(nodeWithExecution)} />)

      // Should render without crashing
      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })

    it('handles completed execution state', () => {
      const nodeWithExecution = {
        ...baseTaskNode,
        __executionState: {
          status: 'completed',
          started_at: '2024-01-01T00:00:00Z',
          completed_at: '2024-01-01T00:01:00Z',
        },
      } as TaskActivity

      render(<TaskReversedStepComponent {...createNodeProps(nodeWithExecution)} />)

      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })

    it('handles failed execution state', () => {
      const nodeWithError = {
        ...baseTaskNode,
        __executionState: {
          status: 'failed',
          error_details: 'Task failed',
          retry_count: 3,
        },
      } as TaskActivity

      render(<TaskReversedStepComponent {...createNodeProps(nodeWithError)} />)

      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })
  })

  describe('Node Structure', () => {
    it('renders with correct structure', () => {
      render(<TaskReversedStepComponent {...createNodeProps(baseTaskNode)} />)

      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })
  })

  describe('Selection State', () => {
    it('renders when selected', () => {
      const props = createNodeProps(baseTaskNode)
      props.selected = true

      render(<TaskReversedStepComponent {...props} />)

      expect(screen.getByText('Loop Back Task')).toBeInTheDocument()
    })
  })
})
