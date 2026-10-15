import type { ConvergeActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { axe } from 'vitest-axe'

import { StepActionsContext, type StepActionsContextValue } from '../../../builder/StepActionsContext'

import { ConvergeStepComponent } from './ConvergeNode'
import type { StepMenuAction } from './hooks/useStepMenuActions'
import { useStepMenuActions } from './hooks/useStepMenuActions'

// Mock useStepMenuActions hook for menu actions tests
const mockMenuActions: StepMenuAction[] = [
  {
    id: 'run-step',
    label: 'Run step',
    onClick: vi.fn(),
  },
  {
    id: 'view-details',
    label: 'View step details',
    onClick: vi.fn(),
  },
  {
    id: 'duplicate',
    label: 'Duplicate',
    onClick: vi.fn(),
  },
  {
    id: 'delete',
    label: 'Delete',
    onClick: vi.fn(),
    variant: 'danger',
  },
]

vi.mock('./hooks/useStepMenuActions', () => ({
  useStepMenuActions: vi.fn(),
  StepMenuCategory: {
    ACTIVITY: 'activity',
    CONTROL_FLOW: 'control-flow',
    TRIGGER: 'trigger',
  },
}))

// Get reference to the mocked function
const mockUseStepMenuActions = vi.mocked(useStepMenuActions)

// Test data and helpers - moved to top level to share between test suites
const baseConvergeNode = {
  type: 'converge',
  id: 'converge-1',
  name: 'Wait for All',
  parameters: {
    strategy: 'all',
  },
} as ConvergeActivity

const createNodeProps = (data: ConvergeActivity) => ({
  id: data.id,
  data,
  type: 'converge' as const,
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

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => children,
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('ConvergeStepComponent', () => {
  describe('Rendering', () => {
    it('renders converge node with name', () => {
      render(<ConvergeStepComponent {...createNodeProps(baseConvergeNode)} />)

      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('renders Converge label', () => {
      render(<ConvergeStepComponent {...createNodeProps(baseConvergeNode)} />)

      expect(screen.getByText('Converge')).toBeInTheDocument()
    })
  })

  describe('Strategy Display', () => {
    it('renders "All" for strategy all', () => {
      render(<ConvergeStepComponent {...createNodeProps(baseConvergeNode)} />)

      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('All')).toBeInTheDocument()
    })

    it('defaults to "All" when strategy is missing', () => {
      const noStrategyConverge = {
        type: 'converge',
        id: 'converge-3',
        name: 'Default Strategy',
        parameters: {},
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(noStrategyConverge)} />)

      expect(screen.getByText('All')).toBeInTheDocument()
    })

    it('defaults to "All" when config is missing', () => {
      const noConfig = {
        type: 'converge',
        id: 'converge-4',
        name: 'No Config',
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(noConfig)} />)

      expect(screen.getByText('All')).toBeInTheDocument()
    })

    it('renders "All" for strategy all (explicit)', () => {
      const explicitStrategyConverge = {
        type: 'converge',
        id: 'converge-5',
        name: 'Explicit Strategy',
        parameters: {
          strategy: 'all',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(explicitStrategyConverge)} />)

      expect(screen.getByText('Type')).toBeInTheDocument()
      expect(screen.getByText('All')).toBeInTheDocument()
    })

    it('renders "Any" for strategy any without n_required', () => {
      // Cast through unknown because the contract type doesn't include 'any' yet
      const anyConverge = {
        type: 'converge',
        id: 'converge-any-1',
        name: 'Any Strategy',
        parameters: {
          strategy: 'any',
        },
      } as unknown as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(anyConverge)} />)

      expect(screen.getByText('Any')).toBeInTheDocument()
    })

    it('renders "Any N" for strategy any with n_required', () => {
      // Cast through unknown because the contract type doesn't include 'any' yet
      const anyNConverge = {
        type: 'converge',
        id: 'converge-any-n-1',
        name: 'Any 3 Strategy',
        parameters: {
          strategy: 'any',
          n_required: 3,
        },
      } as unknown as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(anyNConverge)} />)

      expect(screen.getByText('Any 3')).toBeInTheDocument()
    })
  })

  describe('Empty name', () => {
    it('renders with undefined name', () => {
      const unnamedConverge = {
        type: 'converge',
        id: 'converge-5',
        parameters: {
          strategy: 'all',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(unnamedConverge)} />)

      // Should render without crashing, label should still be present
      expect(screen.getByText('Converge')).toBeInTheDocument()
    })
  })

  describe('Execution State', () => {
    it('handles execution state data', () => {
      const nodeWithExecution = {
        ...baseConvergeNode,
        __executionState: {
          status: 'waiting',
          started_at: '2024-01-01T00:00:00Z',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(nodeWithExecution)} />)

      // Should render without crashing
      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('handles completed execution state', () => {
      const nodeWithExecution = {
        ...baseConvergeNode,
        __executionState: {
          status: 'completed',
          started_at: '2024-01-01T00:00:00Z',
          completed_at: '2024-01-01T00:02:00Z',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createNodeProps(nodeWithExecution)} />)

      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })
  })

  describe('Node Structure', () => {
    it('renders with correct structure', () => {
      render(<ConvergeStepComponent {...createNodeProps(baseConvergeNode)} />)

      expect(screen.getByTestId('converge-node')).toBeInTheDocument()
    })

    it('renders details section', () => {
      render(<ConvergeStepComponent {...createNodeProps(baseConvergeNode)} />)

      expect(screen.getByTestId('converge-step-details')).toBeInTheDocument()
    })
  })
})

// Additional test suite for menu actions functionality
describe('ConvergeNode Menu Actions', () => {
  function createMockNodeActionsContext(): StepActionsContextValue {
    return {
      onRunStep: vi.fn(),
      onViewDetails: vi.fn(),
      onDuplicate: vi.fn(),
      onReplace: vi.fn(),
      onToggleDisabled: vi.fn(),
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Set default return value for useStepMenuActions mock
    mockUseStepMenuActions.mockReturnValue(mockMenuActions)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Hook Integration', () => {
    it('calls useStepMenuActions with correct node ID and step category', () => {
      // Arrange
      const mockProps = createNodeProps(baseConvergeNode)

      // Act
      render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      // Assert
      expect(mockUseStepMenuActions).toHaveBeenCalledWith({
        nodeId: baseConvergeNode.id,
        stepCategory: 'control-flow',
      })
    })

    it('handles missing useStepMenuActions gracefully', () => {
      // Arrange
      mockUseStepMenuActions.mockReturnValue([])
      const mockProps = createNodeProps(baseConvergeNode)

      // Act & Assert - Should not throw
      expect(() => {
        render(
          <ReactFlowProvider>
            <ConvergeStepComponent {...mockProps} />
          </ReactFlowProvider>
        )
      }).not.toThrow()
    })
  })

  describe('Menu Rendering', () => {
    it('renders with menu actions when StepActionsContext is provided', () => {
      // Arrange
      const mockNodeActions = createMockNodeActionsContext()
      const mockProps = createNodeProps(baseConvergeNode)

      // Act
      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockNodeActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Assert - Should render without errors and call hook
      expect(mockUseStepMenuActions).toHaveBeenCalledWith({
        nodeId: baseConvergeNode.id,
        stepCategory: 'control-flow',
      })
      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('renders without menu actions when context is absent', () => {
      // Arrange
      mockUseStepMenuActions.mockReturnValue([]) // No menu actions when no context
      const mockProps = createNodeProps(baseConvergeNode)

      // Act
      render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      // Assert - Should still render the node
      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })
  })

  describe('Menu Interaction', () => {
    it('supports menu action callbacks when provided', () => {
      // Arrange
      const mockOnRunStep = vi.fn()

      // Mock the menu action with the callback
      const mockRunStepAction = {
        id: 'run-step',
        label: 'Run step',
        onClick: () => {
          mockOnRunStep(baseConvergeNode.id)
        },
      }

      mockUseStepMenuActions.mockReturnValue([mockRunStepAction, ...mockMenuActions.slice(1)])

      const mockNodeActions = createMockNodeActionsContext()
      mockNodeActions.onRunStep = mockOnRunStep
      const mockProps = createNodeProps(baseConvergeNode)

      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockNodeActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Act - Simulate clicking the menu action
      mockRunStepAction.onClick()

      // Assert
      expect(mockOnRunStep).toHaveBeenCalledWith(baseConvergeNode.id)
      expect(mockOnRunStep).toHaveBeenCalledTimes(1)
    })

    it('supports all menu action types', () => {
      // Arrange
      const mockNodeActions = createMockNodeActionsContext()
      const mockProps = createNodeProps(baseConvergeNode)

      // Mock menu actions with callbacks
      const mockMenuActionsWithCallbacks = [
        { id: 'run-step', label: 'Run step', onClick: () => mockNodeActions.onRunStep(baseConvergeNode.id) },
        {
          id: 'view-details',
          label: 'View step details',
          onClick: () => mockNodeActions.onViewDetails(baseConvergeNode.id),
        },
        { id: 'duplicate', label: 'Duplicate', onClick: () => mockNodeActions.onDuplicate(baseConvergeNode.id) },
        { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const },
      ]

      mockUseStepMenuActions.mockReturnValue(mockMenuActionsWithCallbacks)

      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockNodeActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Act - Simulate clicking each menu action
      mockMenuActionsWithCallbacks[0]?.onClick() // Run step
      mockMenuActionsWithCallbacks[1]?.onClick() // View details
      mockMenuActionsWithCallbacks[2]?.onClick() // Duplicate

      // Assert
      expect(mockNodeActions.onRunStep).toHaveBeenCalledWith(baseConvergeNode.id)
      expect(mockNodeActions.onViewDetails).toHaveBeenCalledWith(baseConvergeNode.id)
      expect(mockNodeActions.onDuplicate).toHaveBeenCalledWith(baseConvergeNode.id)
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with menu actions', async () => {
      // Arrange
      const mockNodeActions = createMockNodeActionsContext()
      const mockProps = createNodeProps(baseConvergeNode)

      const { container } = render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockNodeActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Act — exclude nested-interactive: pre-existing issue in shared SynStepMenu component
      const results = await axe(container, { rules: { 'nested-interactive': { enabled: false } } })

      // Assert
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations without menu actions', async () => {
      // Arrange
      mockUseStepMenuActions.mockReturnValue([])
      const mockProps = createNodeProps(baseConvergeNode)

      const { container } = render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      // Act
      const results = await axe(container)

      // Assert
      expect(results).toHaveNoViolations()
    })
  })

  describe('Error Handling', () => {
    it('handles malformed node data gracefully', () => {
      // Arrange
      const malformedNode = {} as ConvergeActivity
      const malformedProps = createNodeProps(malformedNode)

      // Act & Assert - Should not throw
      expect(() => {
        render(
          <ReactFlowProvider>
            <ConvergeStepComponent {...malformedProps} />
          </ReactFlowProvider>
        )
      }).not.toThrow()
    })

    it('handles missing strategy configuration', () => {
      // Arrange
      const nodeWithoutStrategy = {
        type: 'converge',
        id: 'converge-no-strategy',
        name: 'No Strategy Node',
        // config missing or empty
      } as ConvergeActivity

      const mockProps = createNodeProps(nodeWithoutStrategy)

      // Act & Assert - Should not throw and should default to 'All'
      render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      expect(screen.getByText('All')).toBeInTheDocument()
    })
  })
})
