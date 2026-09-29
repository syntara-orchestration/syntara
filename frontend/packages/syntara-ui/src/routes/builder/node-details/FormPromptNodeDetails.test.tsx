import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { FormPromptNodeDetails } from './FormPromptNodeDetails'

const mockUpdateActivity = vi.fn()
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (store: { updateActivity: typeof mockUpdateActivity }) => unknown) => {
    const store = {
      updateActivity: mockUpdateActivity,
    }
    return selector ? selector(store) : store
  }),
}))

const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: mockShowError,
  })),
}))

let mockOnSubmitHandler: ((data: Record<string, unknown>) => void) | null = null

vi.mock('../node-forms/FormPromptNodeForm', () => ({
  FormPromptNodeForm: ({
    onSubmit,
    initialData,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    initialData?: Record<string, unknown>
  }) => {
    mockOnSubmitHandler = onSubmit
    return (
      <div data-testid="form-prompt-node-form">
        <span data-testid="initial-name">{initialData?.name as string}</span>
      </div>
    )
  },
}))

describe('FormPromptNodeDetails Component', () => {
  const mockOnClose = vi.fn()

  const createTaskData = (overrides = {}) => ({
    type: 'form_prompt' as const,
    id: 'form-1',
    name: 'Survey',
    parameters: { form_definition: createEmptyFormDefinition() },
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockOnSubmitHandler = null
  })

  it('renders FormPromptNodeForm', () => {
    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('form-prompt-node-form')).toBeInTheDocument()
  })

  it('passes initial data from taskData to form', () => {
    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-name')).toHaveTextContent('Survey')
  })

  it('calls updateActivity when form submits', () => {
    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    const form_definition = createEmptyFormDefinition()
    mockOnSubmitHandler?.({
      name: 'Updated survey',
      form_definition,
      message: 'Please respond',
      fallback_decision: 'submit',
    })

    expect(mockUpdateActivity).toHaveBeenCalledWith(
      'form-1',
      expect.objectContaining({
        name: 'Updated survey',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        parameters: expect.objectContaining({
          form_definition,
          message: 'Please respond',
          fallback_decision: 'submit',
        }),
      })
    )
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('tolerates invalid stored parameters', () => {
    render(
      <FormPromptNodeDetails
        taskData={createTaskData({ parameters: { form_definition: 'not-a-form' } })}
        nodeId="form-1"
        onClose={mockOnClose}
      />
    )

    expect(screen.getByTestId('form-prompt-node-form')).toBeInTheDocument()
  })

  it('shows error when updateActivity throws', () => {
    mockUpdateActivity.mockImplementationOnce(() => {
      throw new Error('The update failed')
    })

    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    mockOnSubmitHandler?.({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
      fallback_decision: 'fallback',
    })

    expect(mockShowError).toHaveBeenCalledWith({ title: 'Update failed', description: 'The update failed' })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
