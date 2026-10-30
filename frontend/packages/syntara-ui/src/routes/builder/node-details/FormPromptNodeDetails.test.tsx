import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { FormFieldTypeEnum } from '../../../forms'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { FormPromptNodeDetails } from './FormPromptNodeDetails'

const mockUpdateActivity = vi.fn()

const validStoredDefinition = {
  fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
}

function buildStoreState(activityParameters?: Record<string, unknown>) {
  return {
    updateActivity: mockUpdateActivity,
    currentWorkflow: {
      workflow: {
        activities: [
          {
            id: 'form-1',
            parameters: activityParameters ?? { form_definition: createEmptyFormDefinition() },
          },
        ],
      },
    },
  }
}

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (state: ReturnType<typeof useWorkflowStore.getState>) => unknown) => {
    const store = buildStoreState() as unknown as ReturnType<typeof useWorkflowStore.getState>
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
let mockInitialData: Record<string, unknown> | undefined

vi.mock('../node-forms/FormPromptNodeForm', () => ({
  FormPromptNodeForm: ({
    onSubmit,
    initialData,
  }: {
    onSubmit: (data: Record<string, unknown>) => void
    initialData?: Record<string, unknown>
  }) => {
    mockOnSubmitHandler = onSubmit
    mockInitialData = initialData
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
    mockInitialData = undefined
    vi.mocked(useWorkflowStore).mockImplementation((selector) => {
      const store = buildStoreState() as unknown as ReturnType<typeof useWorkflowStore.getState>
      return selector ? selector(store) : store
    })
  })

  it('renders FormPromptNodeForm', () => {
    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('form-prompt-node-form')).toBeInTheDocument()
  })

  it('passes initial data from taskData to form', () => {
    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    expect(screen.getByTestId('initial-name')).toHaveTextContent('Survey')
  })

  it('calls onFormDefinitionCommitted when opening with a valid stored definition', () => {
    const onFormDefinitionCommitted = vi.fn()
    vi.mocked(useWorkflowStore).mockImplementation((selector) => {
      const store = buildStoreState({ form_definition: validStoredDefinition }) as unknown as ReturnType<
        typeof useWorkflowStore.getState
      >
      return selector ? selector(store) : store
    })

    render(
      <FormPromptNodeDetails
        taskData={createTaskData({ parameters: { form_definition: createEmptyFormDefinition() } })}
        nodeId="form-1"
        onClose={mockOnClose}
        onFormDefinitionCommitted={onFormDefinitionCommitted}
      />
    )

    expect(onFormDefinitionCommitted).toHaveBeenCalledWith('form-1', validStoredDefinition)
  })

  it('calls updateActivity and onFormDefinitionCommitted when form submits', () => {
    const onFormDefinitionCommitted = vi.fn()
    render(
      <FormPromptNodeDetails
        taskData={createTaskData()}
        nodeId="form-1"
        onClose={mockOnClose}
        onFormDefinitionCommitted={onFormDefinitionCommitted}
      />
    )

    const form_definition = validStoredDefinition
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
    expect(onFormDefinitionCommitted).toHaveBeenCalledWith('form-1', form_definition)
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

  it('loads draft form_definition when strict validation would fail', () => {
    const draftDefinition = {
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'draft_field', label: '' }],
    }
    vi.mocked(useWorkflowStore).mockImplementation((selector) => {
      const store = buildStoreState({ form_definition: draftDefinition }) as unknown as ReturnType<
        typeof useWorkflowStore.getState
      >
      return selector ? selector(store) : store
    })

    render(<FormPromptNodeDetails taskData={createTaskData()} nodeId="form-1" onClose={mockOnClose} />)

    expect(mockInitialData?.form_definition).toEqual(
      expect.objectContaining({
        fields: [expect.objectContaining({ value_name: 'draft_field', label: '' })],
      })
    )
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
