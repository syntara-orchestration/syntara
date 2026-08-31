import type { WorkflowAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { WorkflowSidepanel } from './WorkflowSidepanel'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

// Mock SynCodeBlock component
vi.mock('../../components/details/SynCodeBlock', () => ({
  SynCodeBlock: ({ jsonObject }: { jsonObject: unknown }) => (
    <pre data-testid="code-block">{JSON.stringify(jsonObject)}</pre>
  ),
}))

describe('WorkflowSidepanel', () => {
  const mockOnNameChange = vi.fn()
  const mockOnDescriptionChange = vi.fn()
  const mockOnClose = vi.fn()

  const createMockWorkflow = (overrides?: Record<string, unknown>): WorkflowWithVersion =>
    ({
      id: 'workflow-1',
      name: 'Test Workflow',
      description: 'Test description',
      version: {
        id: 'version-1',
        workflow_id: 'workflow-1',
        workflow_definition: {
          workflow: { activities: [] },
        },
      },
      ...overrides,
    }) as unknown as WorkflowWithVersion

  const defaultProps = {
    workflow: createMockWorkflow(),
    workflowName: 'Test Workflow',
    workflowDescription: 'Test description',
    onNameChange: mockOnNameChange,
    onDescriptionChange: mockOnDescriptionChange,
    onClose: mockOnClose,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the component with title', () => {
    render(<WorkflowSidepanel {...defaultProps} />)

    expect(screen.getByText('Workflow details')).toBeInTheDocument()
  })

  it('renders close button', () => {
    render(<WorkflowSidepanel {...defaultProps} />)

    const closeButton = screen.getByLabelText('Close workflow details')
    expect(closeButton).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<WorkflowSidepanel {...defaultProps} />)

    const closeButton = screen.getByLabelText('Close workflow details')
    await user.click(closeButton)

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('renders workflow name input with value', () => {
    render(<WorkflowSidepanel {...defaultProps} />)

    const nameInput = screen.getByLabelText('Workflow name in workflow details')
    expect(nameInput).toHaveValue('Test Workflow')
  })

  it('calls onNameChange when name input changes', async () => {
    const user = userEvent.setup()
    render(<WorkflowSidepanel {...defaultProps} />)

    const nameInput = screen.getByLabelText('Workflow name in workflow details')
    await user.type(nameInput, 'X')

    expect(mockOnNameChange).toHaveBeenCalledWith('Test WorkflowX')
  })

  it('renders description textarea with value', () => {
    render(<WorkflowSidepanel {...defaultProps} />)

    const descriptionInput = screen.getByLabelText('Description')
    expect(descriptionInput).toHaveValue('Test description')
  })

  it('calls onDescriptionChange when description changes', async () => {
    const user = userEvent.setup()
    render(<WorkflowSidepanel {...defaultProps} />)

    const descriptionInput = screen.getByLabelText('Description')
    await user.type(descriptionInput, 'X')

    expect(mockOnDescriptionChange).toHaveBeenCalledWith('Test descriptionX')
  })

  it('renders workflow definition code block when available', () => {
    const workflow = createMockWorkflow({
      version: {
        id: 'version-1',
        workflow_id: 'workflow-1',
        workflow_definition: {
          workflow: { activities: [{ id: 'activity-1', type: 'task', name: 'Task 1' }] },
        },
      },
    })

    render(<WorkflowSidepanel {...defaultProps} workflow={workflow} />)

    expect(screen.getByText('Workflow definition')).toBeInTheDocument()
    expect(screen.getByTestId('code-block')).toBeInTheDocument()
  })

  it('does not render workflow definition when not available', () => {
    const workflow = createMockWorkflow({
      version: {
        id: 'version-1',
        workflow_id: 'workflow-1',
        // No workflow_definition
      },
    })

    render(<WorkflowSidepanel {...defaultProps} workflow={workflow} />)

    expect(screen.queryByText('Workflow definition')).not.toBeInTheDocument()
  })

  it('does not render workflow definition when version is undefined', () => {
    const workflow = createMockWorkflow({
      version: undefined,
    })

    render(<WorkflowSidepanel {...defaultProps} workflow={workflow} />)

    expect(screen.queryByText('Workflow definition')).not.toBeInTheDocument()
  })

  it('renders form labels correctly', () => {
    render(<WorkflowSidepanel {...defaultProps} />)

    expect(screen.getByText('Workflow name')).toBeInTheDocument()
    expect(screen.getByText('Description')).toBeInTheDocument()
  })

  it('handles empty workflow name', () => {
    render(<WorkflowSidepanel {...defaultProps} workflowName="" />)

    const nameInput = screen.getByLabelText('Workflow name in workflow details')
    expect(nameInput).toHaveValue('')
  })

  it('handles empty workflow description', () => {
    render(<WorkflowSidepanel {...defaultProps} workflowDescription="" />)

    const descriptionInput = screen.getByLabelText('Description')
    expect(descriptionInput).toHaveValue('')
  })
})
