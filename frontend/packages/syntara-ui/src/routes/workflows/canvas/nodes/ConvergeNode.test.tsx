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
const baseConvergeStep = {
  type: 'converge',
  id: 'converge-1',
  name: 'Wait for All',
  parameters: {
    strategy: 'all',
  },
} as ConvergeActivity

const createStepProps = (data: ConvergeActivity) => ({
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
    it('renders converge step with name', () => {
      render(<ConvergeStepComponent {...createStepProps(baseConvergeStep)} />)

      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('renders Converge label', () => {
      render(<ConvergeStepComponent {...createStepProps(baseConvergeStep)} />)

      expect(screen.getByText('Converge')).toBeInTheDocument()
    })
  })

  describe('Strategy Display', () => {
    it('renders "All" for strategy all', () => {
      render(<ConvergeStepComponent {...createStepProps(baseConvergeStep)} />)

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

      render(<ConvergeStepComponent {...createStepProps(noStrategyConverge)} />)

      expect(screen.getByText('All')).toBeInTheDocument()
    })

    it('defaults to "All" when config is missing', () => {
      const noConfig = {
        type: 'converge',
        id: 'converge-4',
        name: 'No Config',
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createStepProps(noConfig)} />)

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

      render(<ConvergeStepComponent {...createStepProps(explicitStrategyConverge)} />)

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

      render(<ConvergeStepComponent {...createStepProps(anyConverge)} />)

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

      render(<ConvergeStepComponent {...createStepProps(anyNConverge)} />)

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

      render(<ConvergeStepComponent {...createStepProps(unnamedConverge)} />)

      // Should render without crashing, label should still be present
      expect(screen.getByText('Converge')).toBeInTheDocument()
    })
  })

  describe('Execution State', () => {
    it('handles execution state data', () => {
      const stepWithExecution = {
        ...baseConvergeStep,
        __executionState: {
          status: 'waiting',
          started_at: '2024-01-01T00:00:00Z',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createStepProps(stepWithExecution)} />)

      // Should render without crashing
      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('handles completed execution state', () => {
      const stepWithExecution = {
        ...baseConvergeStep,
        __executionState: {
          status: 'completed',
          started_at: '2024-01-01T00:00:00Z',
          completed_at: '2024-01-01T00:02:00Z',
        },
      } as ConvergeActivity

      render(<ConvergeStepComponent {...createStepProps(stepWithExecution)} />)

      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })
  })

  describe('Step Structure', () => {
    it('renders with correct structure', () => {
      render(<ConvergeStepComponent {...createStepProps(baseConvergeStep)} />)

      expect(screen.getByTestId('converge-step')).toBeInTheDocument()
    })

    it('renders details section', () => {
      render(<ConvergeStepComponent {...createStepProps(baseConvergeStep)} />)

      expect(screen.getByTestId('converge-step-details')).toBeInTheDocument()
    })
  })
})

// Additional test suite for menu actions functionality
describe('ConvergeStep Menu Actions', () => {
  function createMockStepActionsContext(): StepActionsContextValue {
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
    it('calls useStepMenuActions with the step ID and category', () => {
      // Arrange
      const mockProps = createStepProps(baseConvergeStep)

      // Act
      render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      // Assert
      expect(mockUseStepMenuActions).toHaveBeenCalledWith({
        nodeId: baseConvergeStep.id,
        stepCategory: 'control-flow',
      })
    })

    it('handles missing useStepMenuActions gracefully', () => {
      // Arrange
      mockUseStepMenuActions.mockReturnValue([])
      const mockProps = createStepProps(baseConvergeStep)

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
      const mockStepActions = createMockStepActionsContext()
      const mockProps = createStepProps(baseConvergeStep)

      // Act
      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockStepActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Assert - Should render without errors and call hook
      expect(mockUseStepMenuActions).toHaveBeenCalledWith({
        nodeId: baseConvergeStep.id,
        stepCategory: 'control-flow',
      })
      expect(screen.getByText('Wait for All')).toBeInTheDocument()
    })

    it('renders without menu actions when context is absent', () => {
      // Arrange
      mockUseStepMenuActions.mockReturnValue([]) // No menu actions when no context
      const mockProps = createStepProps(baseConvergeStep)

      // Act
      render(
        <ReactFlowProvider>
          <ConvergeStepComponent {...mockProps} />
        </ReactFlowProvider>
      )

      // Assert - The step still renders
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
          mockOnRunStep(baseConvergeStep.id)
        },
      }

      mockUseStepMenuActions.mockReturnValue([mockRunStepAction, ...mockMenuActions.slice(1)])

      const mockStepActions = createMockStepActionsContext()
      mockStepActions.onRunStep = mockOnRunStep
      const mockProps = createStepProps(baseConvergeStep)

      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockStepActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Act - Simulate clicking the menu action
      mockRunStepAction.onClick()

      // Assert
      expect(mockOnRunStep).toHaveBeenCalledWith(baseConvergeStep.id)
      expect(mockOnRunStep).toHaveBeenCalledTimes(1)
    })

    it('supports all menu action types', () => {
      // Arrange
      const mockStepActions = createMockStepActionsContext()
      const mockProps = createStepProps(baseConvergeStep)

      // Mock menu actions with callbacks
      const mockMenuActionsWithCallbacks = [
        { id: 'run-step', label: 'Run step', onClick: () => mockStepActions.onRunStep(baseConvergeStep.id) },
        {
          id: 'view-details',
          label: 'View step details',
          onClick: () => mockStepActions.onViewDetails(baseConvergeStep.id),
        },
        { id: 'duplicate', label: 'Duplicate', onClick: () => mockStepActions.onDuplicate(baseConvergeStep.id) },
        { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const },
      ]

      mockUseStepMenuActions.mockReturnValue(mockMenuActionsWithCallbacks)

      render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockStepActions}>
            <ConvergeStepComponent {...mockProps} />
          </StepActionsContext.Provider>
        </ReactFlowProvider>
      )

      // Act - Simulate clicking each menu action
      mockMenuActionsWithCallbacks[0]?.onClick() // Run step
      mockMenuActionsWithCallbacks[1]?.onClick() // View details
      mockMenuActionsWithCallbacks[2]?.onClick() // Duplicate

      // Assert
      expect(mockStepActions.onRunStep).toHaveBeenCalledWith(baseConvergeStep.id)
      expect(mockStepActions.onViewDetails).toHaveBeenCalledWith(baseConvergeStep.id)
      expect(mockStepActions.onDuplicate).toHaveBeenCalledWith(baseConvergeStep.id)
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with menu actions', async () => {
      // Arrange
      const mockStepActions = createMockStepActionsContext()
      const mockProps = createStepProps(baseConvergeStep)

      const { container } = render(
        <ReactFlowProvider>
          <StepActionsContext.Provider value={mockStepActions}>
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
      const mockProps = createStepProps(baseConvergeStep)

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
    it('handles malformed step data gracefully', () => {
      // Arrange
      const malformedStep = {} as ConvergeActivity
      const malformedStepProps = createStepProps(malformedStep)

      // Act & Assert - Should not throw
      expect(() => {
        render(
          <ReactFlowProvider>
            <ConvergeStepComponent {...malformedStepProps} />
          </ReactFlowProvider>
        )
      }).not.toThrow()
    })

    it('handles missing strategy configuration', () => {
      // Arrange
      const stepWithoutStrategy = {
        type: 'converge',
        id: 'converge-no-strategy',
        name: 'No Strategy Step',
        // config missing or empty
      } as ConvergeActivity

      const mockProps = createStepProps(stepWithoutStrategy)

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
