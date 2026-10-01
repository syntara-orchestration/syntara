import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AddStepPanel, AddStepPanelHeader } from './AddStepPanel'

const { mockStepRegistryGetAll, mockStepRegistryGet } = vi.hoisted(() => ({
  mockStepRegistryGetAll: vi.fn(),
  mockStepRegistryGet: vi.fn(),
}))

vi.mock('./registry/StepRegistry', () => ({
  StepRegistry: {
    getAll: mockStepRegistryGetAll,
    get: mockStepRegistryGet,
  },
}))

const mockStepTypes = [
  {
    id: 'action',
    label: 'Action',
    icon: () => <div>ActionIcon</div>,
    category: 'task',
    description: 'Execute scripts or make API calls',
    order: 30,
    formComponent: () => null,
    onSubmit: vi.fn(),
  },
  {
    id: 'trigger',
    label: 'Trigger',
    icon: () => <div>TriggerIcon</div>,
    category: 'trigger',
    description: 'Start the workflow',
    order: 10,
    formComponent: () => null,
    onSubmit: vi.fn(),
    subtypes: [
      {
        id: 'trigger-manual',
        label: 'Manual',
        icon: () => <div>ManualIcon</div>,
      },
    ],
  },
]

describe('AddStepPanelHeader', () => {
  const mockOnBack = vi.fn()
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the panel title', () => {
    render(
      <AddStepPanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowSteps={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByText('Add step')).toBeInTheDocument()
  })

  it('shows back button when showing subtypes and not hasNoWorkflowSteps', () => {
    render(
      <AddStepPanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowSteps={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()
  })

  it('does not show back button when hasNoWorkflowSteps', () => {
    render(
      <AddStepPanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowSteps
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.queryByRole('button', { name: /Back/i })).not.toBeInTheDocument()
  })

  it('shows close button when not hasNoWorkflowSteps', () => {
    render(
      <AddStepPanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowSteps={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByRole('button', { name: /Close add step panel/i })).toBeInTheDocument()
  })

  it('hides close button when hasNoWorkflowSteps', () => {
    render(
      <AddStepPanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowSteps
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.queryByRole('button', { name: /Close add step panel/i })).not.toBeInTheDocument()
  })

  it('calls onBack when back button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <AddStepPanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowSteps={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Back/i }))

    expect(mockOnBack).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <AddStepPanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowSteps={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Close add step panel/i }))

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })
})

describe('AddStepPanel Component', () => {
  const mockOnClose = vi.fn()
  const mockOnSelectNode = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockStepRegistryGetAll.mockReturnValue(mockStepTypes)
    mockStepRegistryGet.mockImplementation((id: string) => mockStepTypes.find((node) => node.id === id) as never)
  })

  it('renders the panel with title and close button', () => {
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} />)

    expect(screen.getByText('Add step')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Close add step panel/i })).toBeInTheDocument()
  })

  it('calls onSelectStep when a base node is selected', async () => {
    const user = userEvent.setup()
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Action' }))

    expect(mockOnSelectNode).toHaveBeenCalledWith('action', null)
  })

  it('shows subtypes and calls onSelectStep with subtype', async () => {
    const user = userEvent.setup()
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Trigger' }))
    await user.click(screen.getByRole('button', { name: 'Manual' }))

    expect(mockOnSelectNode).toHaveBeenCalledWith('trigger', 'trigger-manual')
  })

  it('shows back button for subtype list and returns to main list', async () => {
    const user = userEvent.setup()
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Trigger' }))

    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Back/i }))

    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })

  it('filters to trigger types when the canvas has no workflow steps yet', () => {
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} hasNoWorkflowSteps />)

    expect(screen.getByRole('button', { name: 'Manual' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Action' })).not.toBeInTheDocument()
  })

  it('hides close and back buttons when the canvas has no workflow steps yet', () => {
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} hasNoWorkflowSteps />)

    expect(screen.queryByRole('button', { name: /Close add step panel/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Back/i })).not.toBeInTheDocument()
  })

  it('filters out triggers when adding from edge', () => {
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} sourceNodeId="node-123" />)

    expect(screen.queryByRole('button', { name: 'Trigger' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })

  it('filters out triggers when replacing a generic step', () => {
    render(<AddStepPanel onClose={mockOnClose} onSelectStep={mockOnSelectNode} replacementNodeId="node-456" />)

    expect(screen.queryByRole('button', { name: 'Trigger' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })
})
