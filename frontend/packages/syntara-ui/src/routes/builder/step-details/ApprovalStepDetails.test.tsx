import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { ApprovalStepDetails } from './ApprovalStepDetails'

// Mock the workflow store
const mockUpdateActivity = vi.fn()
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (store: { updateActivity: typeof mockUpdateActivity }) => unknown) => {
    const store = {
      updateActivity: mockUpdateActivity,
    }
    return selector ? selector(store) : store
  }),
}))

// Mock the alerts hook
const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: mockShowError,
  })),
}))

// Mock ApprovalStepForm - simulates auto-save behavior
let mockOnSubmitHandler: ((data: Record<string, unknown>) => void) | null = null

vi.mock('../step-forms/ApprovalStepForm', () => ({
  ApprovalStepForm: ({
    onSubmit,
    initialData,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    initialData?: Record<string, unknown>
  }) => {
    mockOnSubmitHandler = onSubmit
    return (
      <div data-testid="approval-step-form">
        <span data-testid="initial-name">{initialData?.name as string}</span>
      </div>
    )
  },
}))

describe('ApprovalStepDetails Component', () => {
  const mockOnClose = vi.fn()

  const createTaskData = (overrides = {}) => ({
    type: 'approval' as const,
    id: 'approval-1',
    name: 'Test Approval',
    parameters: {},
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders ApprovalStepForm', () => {
    render(<ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('approval-step-form')).toBeInTheDocument()
  })

  it('passes initial data from taskData to form', () => {
    render(<ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-name')).toHaveTextContent('Test Approval')
  })

  it('calls updateActivity when form auto-saves', () => {
    render(<ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />)

    mockOnSubmitHandler?.({
      name: 'Updated Approval',
      approver_users: ['admin'],
      approver_groups: [],
      prompt: 'Please approve',
    })

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'approval-1',
      expect.objectContaining({
        name: 'Updated Approval',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          approver_users: ['admin'],
          // approver_groups is omitted when empty
          prompt: 'Please approve',
        }),
      })
    )
  })

  it('calls onClose after auto-save', () => {
    render(<ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />)

    mockOnSubmitHandler?.({
      name: 'Updated Approval',
      approver_users: ['admin'],
      approver_groups: [],
      prompt: 'Please approve',
    })

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('handles taskData without parameters', () => {
    const taskDataWithoutConfig = createTaskData({ parameters: undefined })

    render(<ApprovalStepDetails taskData={taskDataWithoutConfig} nodeId="approval-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('approval-step-form')).toBeInTheDocument()
  })

  it('shows error when updateActivity throws', () => {
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })

    render(<ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />)

    mockOnSubmitHandler?.({
      name: 'Test Approval',
      approver_users: ['user1'],
      approver_groups: [],
      prompt: 'Approve',
    })

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  it('passes settings from taskData to form', () => {
    const taskDataWithSettings = createTaskData({
      parameters: { decision_window: 7200 },
      settings: { continue_on_failure: true },
    })

    render(<ApprovalStepDetails taskData={taskDataWithSettings} nodeId="approval-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('approval-step-form')).toBeInTheDocument()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <ApprovalStepDetails taskData={createTaskData()} nodeId="approval-1" onClose={mockOnClose} />
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
