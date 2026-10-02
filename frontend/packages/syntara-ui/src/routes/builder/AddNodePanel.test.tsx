import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AddNodePanel, AddNodePanelHeader } from './AddNodePanel'

const { mockNodeRegistryGetAll, mockNodeRegistryGet } = vi.hoisted(() => ({
  mockNodeRegistryGetAll: vi.fn(),
  mockNodeRegistryGet: vi.fn(),
}))

vi.mock('./registry/NodeRegistry', () => ({
  NodeRegistry: {
    getAll: mockNodeRegistryGetAll,
    get: mockNodeRegistryGet,
  },
}))

const mockNodeTypes = [
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
        description: 'Start the workflow manually',
      },
    ],
  },
  {
    id: 'terraform',
    label: 'Terraform Enterprise',
    icon: () => <div>TerraformIcon</div>,
    category: 'action',
    description: 'Manage Terraform Enterprise workspaces',
    keywords: ['terraform', 'tfe'],
    order: 45,
    selectionTitle: 'Select a Terraform step',
    formComponent: () => null,
    onSubmit: vi.fn(),
    subtypes: [
      {
        id: 'tfe-create-workspace',
        label: 'Create Workspace',
        icon: () => <div>CreateWorkspaceIcon</div>,
        description: 'Create a TFE workspace',
      },
      {
        id: 'tfe-link-vcs',
        label: 'Link VCS to Workspace',
        icon: () => <div>LinkVcsIcon</div>,
        description: 'Link a GitHub repo to a workspace',
      },
    ],
  },
]

describe('AddNodePanelHeader', () => {
  const mockOnBack = vi.fn()
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the panel title', () => {
    render(
      <AddNodePanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowNodes={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByText('Add step')).toBeInTheDocument()
  })

  it('shows back button when showing subtypes and not hasNoWorkflowNodes', () => {
    render(
      <AddNodePanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowNodes={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()
  })

  it('does not show back button when hasNoWorkflowNodes', () => {
    render(
      <AddNodePanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowNodes
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.queryByRole('button', { name: /Back/i })).not.toBeInTheDocument()
  })

  it('shows close button when not hasNoWorkflowNodes', () => {
    render(
      <AddNodePanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowNodes={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByRole('button', { name: /Close add step panel/i })).toBeInTheDocument()
  })

  it('hides close button when hasNoWorkflowNodes', () => {
    render(
      <AddNodePanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowNodes
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    expect(screen.queryByRole('button', { name: /Close add step panel/i })).not.toBeInTheDocument()
  })

  it('calls onBack when back button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <AddNodePanelHeader
        panelTitle="Select a step"
        isShowingSubtypeList
        hasNoWorkflowNodes={false}
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
      <AddNodePanelHeader
        panelTitle="Add step"
        isShowingSubtypeList={false}
        hasNoWorkflowNodes={false}
        onBack={mockOnBack}
        onClose={mockOnClose}
      />
    )

    await user.click(screen.getByRole('button', { name: /Close add step panel/i }))

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })
})

describe('AddNodePanel Component', () => {
  const mockOnClose = vi.fn()
  const mockOnSelectNode = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockNodeRegistryGetAll.mockReturnValue(mockNodeTypes)
    mockNodeRegistryGet.mockImplementation((id: string) => mockNodeTypes.find((node) => node.id === id) as never)
  })

  it('renders the panel with title and close button', () => {
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    expect(screen.getByText('Add step')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Close add step panel/i })).toBeInTheDocument()
  })

  it('calls onSelectNode when a base node is selected', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Action' }))

    expect(mockOnSelectNode).toHaveBeenCalledWith('action', null)
  })

  it('shows subtypes and calls onSelectNode with subtype', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Trigger' }))
    await user.click(screen.getByRole('button', { name: 'Manual' }))

    expect(mockOnSelectNode).toHaveBeenCalledWith('trigger', 'trigger-manual')
  })

  it('shows back button for subtype list and returns to main list', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Trigger' }))

    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Back/i }))

    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })

  it('filters to trigger types when the canvas has no workflow steps yet', () => {
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} hasNoWorkflowNodes />)

    expect(screen.getByRole('button', { name: 'Manual' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Action' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Search...' })).not.toBeInTheDocument()
  })

  it('hides close and back buttons when the canvas has no workflow steps yet', () => {
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} hasNoWorkflowNodes />)

    expect(screen.queryByRole('button', { name: /Close add step panel/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Back/i })).not.toBeInTheDocument()
  })

  it('filters out triggers when adding from edge', () => {
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} sourceNodeId="node-123" />)

    expect(screen.queryByRole('button', { name: 'Trigger' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })

  it('filters the catalog and shows an empty state', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.type(screen.getByRole('textbox', { name: 'Search...' }), 'terraform')

    expect(screen.getByRole('button', { name: 'Terraform Enterprise' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Action' })).not.toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: 'Search...' }), 'zzz')

    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('includes matching Terraform actions in the catalog results', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.type(screen.getByRole('textbox', { name: 'Search...' }), 'github')

    expect(screen.getByRole('button', { name: 'Link VCS to Workspace' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Action' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create Workspace' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Link VCS to Workspace' }))

    expect(mockOnSelectNode).toHaveBeenCalledWith('terraform', 'tfe-link-vcs')
  })

  it('filters Terraform actions in the step list', async () => {
    const user = userEvent.setup()
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Terraform Enterprise' }))
    await user.type(screen.getByRole('textbox', { name: 'Search actions...' }), 'github')

    expect(screen.getByRole('button', { name: 'Link VCS to Workspace' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create Workspace' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('filters out triggers when replacing a generic step', () => {
    render(<AddNodePanel onClose={mockOnClose} onSelectNode={mockOnSelectNode} replacementNodeId="node-456" />)

    expect(screen.queryByRole('button', { name: 'Trigger' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })
})
