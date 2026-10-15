import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ConditionStepDetails } from './ConditionStepDetails'

// Mock the workflow store
const mockUpdateActivity = vi.fn()
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (store: { updateActivity: typeof mockUpdateActivity }) => unknown) => {
    const store = {
      updateActivity: mockUpdateActivity,
    }
    return selector ? selector(store) : store
  }),
  useWorkflowStoreActions: vi.fn(() => ({
    updateActivity: mockUpdateActivity,
  })),
}))

// Mock the alerts hook
const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: mockShowError,
  })),
}))

// Mock ConditionStepForm - simulates auto-save behavior
let mockOnSubmitHandler: ((data: Record<string, unknown>) => void) | null = null

vi.mock('../step-forms/ConditionStepForm', () => ({
  ConditionStepForm: ({ onSubmit }: { onSubmit: (data: Record<string, unknown>) => void }) => {
    mockOnSubmitHandler = onSubmit
    return <div data-testid="condition-step-form" />
  },
}))

describe('ConditionStepDetails Component', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders ConditionStepForm', () => {
    const conditionData = {
      type: 'condition' as const,
      id: 'condition-1',
      name: 'Test Condition',
      parameters: { condition: 'input.value > 10' },
    }

    render(<ConditionStepDetails conditionData={conditionData} nodeId="condition-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('condition-step-form')).toBeInTheDocument()
  })

  it('calls updateActivity when form auto-saves', () => {
    const conditionData = {
      type: 'condition' as const,
      id: 'condition-1',
      name: 'Original Condition',
      parameters: { condition: 'input.value > 5' },
    }

    render(<ConditionStepDetails conditionData={conditionData} nodeId="condition-1" onClose={mockOnClose} />)

    // Simulate auto-save
    mockOnSubmitHandler?.({ name: 'Updated Condition', condition: 'true' })

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'condition-1',
      expect.objectContaining({
        id: 'condition-1',
        type: 'condition',
        name: 'Updated Condition',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          condition: 'true',
        }),
      })
    )
  })

  it('renders form with initial data', () => {
    const conditionData = {
      type: 'condition' as const,
      id: 'condition-1',
      name: 'Condition',
      parameters: { condition: 'test' },
    }

    render(<ConditionStepDetails conditionData={conditionData} nodeId="condition-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('condition-step-form')).toBeInTheDocument()
  })

  it('shows error when updateActivity throws', () => {
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })
    const conditionData = {
      type: 'condition' as const,
      id: 'condition-1',
      name: 'Condition',
      parameters: { condition: 'test' },
    }

    render(<ConditionStepDetails conditionData={conditionData} nodeId="condition-1" onClose={mockOnClose} />)

    // Simulate auto-save
    mockOnSubmitHandler?.({ name: 'Condition', condition: 'test' })

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })
})
