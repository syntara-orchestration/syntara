import type { LoopActivity } from '@syntara/contracts'
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useExecutionStore } from '../../stores/useExecutionStore'

import { LoopStepComponent } from './LoopNode'

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  useEdges: () => [],
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('LoopStepComponent', () => {
  const baseLoopNode = {
    type: 'loop',
    id: 'loop-1',
    name: 'Process Items',
    parameters: {
      type: 'for_each',
      items: '{{ items }}',
    },
  } as LoopActivity

  const createNodeProps = (data: LoopActivity) => ({
    id: data.id,
    data,
    type: 'loop' as const,
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
    it('renders loop node with name', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('Process Items')).toBeInTheDocument()
    })

    it('renders Loop subtitle label', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      // "Loop" appears both as subtitle and as branch handle, so look for both
      const loopTexts = screen.getAllByText('Loop')
      expect(loopTexts.length).toBeGreaterThanOrEqual(1)
    })

    it('renders Done and Loop branch handles', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('Done')).toBeInTheDocument()
      // Loop appears multiple times
      const loopTexts = screen.getAllByText('Loop')
      expect(loopTexts.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Branch Handles', () => {
    it('renders Done branch handle', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('Done')).toBeInTheDocument()
    })
  })

  describe('Empty name', () => {
    it('renders with empty name', () => {
      const unnamedLoop = {
        type: 'loop',
        id: 'loop-2',
        parameters: {
          type: 'for_each',
          items: '{{ data }}',
        },
      } as LoopActivity

      render(<LoopStepComponent {...createNodeProps(unnamedLoop)} />)

      // Should render without crashing, label should still be present
      const loopTexts = screen.getAllByText('Loop')
      expect(loopTexts.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Execution State', () => {
    it('handles execution state data', () => {
      const nodeWithExecution = {
        ...baseLoopNode,
        __executionState: {
          status: 'completed',
          started_at: '2024-01-01T00:00:00Z',
          completed_at: '2024-01-01T00:01:00Z',
        },
      } as LoopActivity

      render(<LoopStepComponent {...createNodeProps(nodeWithExecution)} />)

      // Should render without crashing
      expect(screen.getByText('Process Items')).toBeInTheDocument()
    })

    it('handles execution state with retry count', () => {
      const nodeWithRetry = {
        ...baseLoopNode,
        __executionState: {
          status: 'running',
          retry_count: 2,
        },
      } as LoopActivity

      render(<LoopStepComponent {...createNodeProps(nodeWithRetry)} />)

      expect(screen.getByText('Process Items')).toBeInTheDocument()
    })
  })

  describe('Node Structure', () => {
    it('renders with correct structure', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('Process Items')).toBeInTheDocument()
    })
  })

  describe('Iteration Badge', () => {
    afterEach(() => {
      act(() => {
        useExecutionStore.setState({ activityStates: new Map() })
      })
    })

    it('does not render badge when no execution state', () => {
      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument()
    })

    it('renders badge with iteration count during running loop', () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            [
              'loop-1',
              {
                activityId: 'loop-1',
                status: 'running' as const,
                outputData: { iteration_count: 2 },
              },
            ],
          ]),
        })
      })

      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('3')).toBeInTheDocument()
    })

    it('uses singular "loop iteration" in screen reader text for count of 1', () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            [
              'loop-1',
              {
                activityId: 'loop-1',
                status: 'running' as const,
                outputData: { iteration_count: 0 },
              },
            ],
          ]),
        })
      })

      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('1 loop iteration')).toBeInTheDocument()
    })

    it('uses plural "loop iterations" in screen reader text for count > 1', () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            [
              'loop-1',
              {
                activityId: 'loop-1',
                status: 'completed' as const,
                outputData: { iteration_count: 5, iteration_results: {} },
              },
            ],
          ]),
        })
      })

      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('5')).toBeInTheDocument()
      expect(screen.getByText('5 loop iterations')).toBeInTheDocument()
    })

    it('renders badge with 1-indexed count for failed loop', () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            [
              'loop-1',
              {
                activityId: 'loop-1',
                status: 'failed' as const,
                outputData: { iteration_count: 3 },
              },
            ],
          ]),
        })
      })

      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('4')).toBeInTheDocument()
    })

    it('has no accessibility violations when badge is visible', async () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            ['loop-1', { activityId: 'loop-1', status: 'running' as const, outputData: { iteration_count: 2 } }],
          ]),
        })
      })

      const { container } = render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(await axe(container)).toHaveNoViolations()
    })

    it('renders badge with total count for completed loop', () => {
      act(() => {
        useExecutionStore.setState({
          activityStates: new Map([
            [
              'loop-1',
              {
                activityId: 'loop-1',
                status: 'completed' as const,
                outputData: { iteration_count: 5, iteration_results: {} },
              },
            ],
          ]),
        })
      })

      render(<LoopStepComponent {...createNodeProps(baseLoopNode)} />)

      expect(screen.getByText('5')).toBeInTheDocument()
    })
  })
})
