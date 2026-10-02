import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { ConvergeStepDetails } from './ConvergeStepDetails'

// Mock the workflow store
const mockUpdateActivity = vi.fn()
vi.mock('../../../stores/useWorkflowStore', () => ({
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

// Mock ConvergeStepForm - simulates auto-save behavior
let mockOnSubmitHandler: ((data: Record<string, unknown>) => void) | null = null

vi.mock('../step-forms/ConvergeStepForm', () => ({
  ConvergeStepForm: ({
    onSubmit,
    initialData,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    initialData?: {
      name?: string
      strategy?: string
      requiredPathCount?: number
      [key: string]: unknown
    }
  }) => {
    mockOnSubmitHandler = onSubmit
    return (
      <div data-testid="converge-step-form">
        <span data-testid="initial-name">{initialData?.name ?? ''}</span>
        <span data-testid="initial-required-path-count">{String(initialData?.requiredPathCount ?? '')}</span>
      </div>
    )
  },
}))

describe('ConvergeStepDetails Component', () => {
  const mockOnClose = vi.fn()

  const createConvergeData = (overrides = {}) => ({
    type: 'converge' as const,
    id: 'converge-1',
    name: 'Test Converge',
    parameters: {
      strategy: 'all' as const,
      branches: ['branch-1', 'branch-2'],
    },
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders ConvergeStepForm', () => {
    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('converge-step-form')).toBeInTheDocument()
  })

  it('passes initial data from convergeData to form', () => {
    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-name')).toHaveTextContent('Test Converge')
  })

  it('calls updateActivity when form auto-saves', () => {
    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    // Simulate auto-save with strategy
    mockOnSubmitHandler?.({
      name: 'Test Converge',
      strategy: 'all',
    })

    // Verify updateActivity was called with correct node ID and payload structure
    expect(mockUpdateActivity).toHaveBeenCalledTimes(1)
    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'converge-1',
      expect.objectContaining({
        type: 'converge',
        name: 'Test Converge',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          strategy: 'all',
        }),
      })
    )

    // Verify the actual payload structure from handleSubmit (not just initialData passthrough)
    const actualPayload = mockUpdateActivity.mock.calls[0][1] as {
      type: string
      name: string
      parameters: { strategy: string }
    }
    expect(actualPayload.type).toBe('converge')
    expect(actualPayload.name).toBe('Test Converge')
    expect(actualPayload.parameters.strategy).toBe('all')
  })

  it('calls onClose after auto-save', () => {
    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    // Simulate auto-save
    mockOnSubmitHandler?.({
      name: 'Test Converge',
      strategy: 'all',
    })

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('renders form with initial data', () => {
    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('converge-step-form')).toBeInTheDocument()
  })

  it('handles convergeData without config object', () => {
    const convergeDataWithoutConverge = createConvergeData({ parameters: {} })

    render(<ConvergeStepDetails convergeData={convergeDataWithoutConverge} nodeId="converge-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('converge-step-form')).toBeInTheDocument()
  })

  it('shows error when updateActivity throws', () => {
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })

    render(<ConvergeStepDetails convergeData={createConvergeData()} nodeId="converge-1" onClose={mockOnClose} />)

    // Simulate auto-save
    mockOnSubmitHandler?.({
      name: 'Test Converge',
      strategy: 'all',
    })

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  it('defaults requiredPathCount to 1 in edit form when not previously set', () => {
    render(
      <ConvergeStepDetails
        convergeData={createConvergeData({ parameters: { strategy: 'all', branches: [] } })}
        nodeId="converge-1"
        onClose={mockOnClose}
      />
    )

    expect(screen.getByTestId('initial-required-path-count')).toHaveTextContent('1')
  })

  describe('n_required field handling', () => {
    it('reads n_required from config field', () => {
      const convergeData = createConvergeData({
        parameters: {
          strategy: 'any',
          branches: ['a', 'b', 'c'],
          n_required: 2,
        },
      })

      render(<ConvergeStepDetails convergeData={convergeData} nodeId="converge-1" onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-required-path-count')).toHaveTextContent('2')
    })

    it('defaults requiredPathCount to 1 when n_required is absent', () => {
      const convergeData = createConvergeData({
        parameters: {
          strategy: 'any',
          branches: ['a', 'b', 'c'],
        },
      })

      render(<ConvergeStepDetails convergeData={convergeData} nodeId="converge-1" onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-required-path-count')).toHaveTextContent('1')
    })

    it('reads n_required with other config fields present', () => {
      const convergeData = createConvergeData({
        parameters: {
          strategy: 'any',
          branches: ['a', 'b', 'c'],
          n_required: 4,
        },
      })

      render(<ConvergeStepDetails convergeData={convergeData} nodeId="converge-1" onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-required-path-count')).toHaveTextContent('4')
    })

    it('writes n_required in config when saving with any strategy', () => {
      const convergeData = createConvergeData({
        parameters: {
          strategy: 'any',
          branches: ['a', 'b', 'c'],
          n_required: 3,
        },
      })

      render(<ConvergeStepDetails convergeData={convergeData} nodeId="converge-1" onClose={mockOnClose} />)

      mockOnSubmitHandler?.({
        name: 'Test Converge',
        strategy: 'any',
        requiredPathCount: 3,
      })

      expect(mockUpdateActivity).toHaveBeenCalledWith(
        'converge-1',
        expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          parameters: expect.objectContaining({
            strategy: 'any',
            n_required: 3,
          }),
        })
      )
    })

    it('omits n_required from config when strategy is all', () => {
      const convergeData = createConvergeData({
        parameters: {
          strategy: 'all',
          branches: ['a', 'b', 'c'],
        },
      })

      render(<ConvergeStepDetails convergeData={convergeData} nodeId="converge-1" onClose={mockOnClose} />)

      mockOnSubmitHandler?.({
        name: 'Test Converge',
        strategy: 'all',
      })

      const actualPayload = mockUpdateActivity.mock.calls[0][1] as {
        parameters: Record<string, unknown>
      }
      expect(actualPayload.parameters.n_required).toBeUndefined()
    })
  })
})
