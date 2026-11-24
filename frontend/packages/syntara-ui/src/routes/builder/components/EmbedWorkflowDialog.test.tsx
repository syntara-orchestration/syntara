import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useEmbeddableWorkflows } from '../useEmbeddableWorkflows'

import { EmbedWorkflowDialog } from './EmbedWorkflowDialog'

const mocks = vi.hoisted(() => ({
  insertEmbeddedGraph: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  get: vi.fn(),
}))

vi.mock('../useEmbeddableWorkflows', () => ({ useEmbeddableWorkflows: vi.fn() }))
vi.mock('../useEmbedWorkflow', () => ({ useEmbedWorkflow: () => ({ insertEmbeddedGraph: mocks.insertEmbeddedGraph }) }))
vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))
vi.mock('../../../client', () => ({ workflowFetchClient: { GET: mocks.get } }))

// Deterministic picker: render the real toggle, plus each SelectOption as a role="option"
// button wired to onSelect. Avoids driving PatternFly's popper in jsdom; the real picker
// is covered by SynSelect's own tests.
vi.mock('../../../components/SynSelect', () => ({
  SynSelect: ({
    onSelect,
    children,
    toggle,
  }: {
    onSelect?: (event: unknown, value: unknown) => void
    children?: unknown
    toggle?: (ref: unknown) => ReactNode
  }) => {
    const options: Array<{ value: string; label: string }> = []
    const collect = (node: unknown): void => {
      if (node == null || typeof node !== 'object') return
      if (Array.isArray(node)) {
        node.forEach(collect)
        return
      }
      const props = (node as { props?: { value?: unknown; children?: unknown } }).props
      if (typeof props?.value === 'string' && typeof props?.children === 'string') {
        options.push({ value: props.value, label: props.children })
      }
      if (props?.children != null) collect(props.children)
    }
    collect(children)
    return (
      <div>
        {toggle?.(() => {})}
        {options.map((o) => (
          <button type="button" key={o.value} onClick={(event) => onSelect?.(event, o.value)}>
            {o.label}
          </button>
        ))}
      </div>
    )
  },
}))

const mockUseEmbeddable = vi.mocked(useEmbeddableWorkflows)

const withWorkflows = () =>
  mockUseEmbeddable.mockReturnValue({
    workflows: [{ id: 'wf-a', name: 'Alpha', published_version_number: 2 }] as never,
    isLoading: false,
    isError: false,
    error: null,
  })

const resolveDefinition = (definition: unknown) =>
  mocks.get.mockResolvedValue({ data: { workflow_definition: definition }, error: undefined })

const selectAlpha = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: 'Alpha' }))

describe('EmbedWorkflowDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockResolvedValue({
      data: { workflow_definition: { nodes: [], edges: [], triggers: [] } },
      error: undefined,
    })
  })

  it('shows the picker placeholder and disables Embed until a workflow is chosen', () => {
    withWorkflows()
    render(<EmbedWorkflowDialog isOpen onClose={vi.fn()} projectId="project-1" currentWorkflowId="self" />)

    expect(screen.getByRole('button', { name: /select a published workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Embed workflow' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('surfaces an error when the project workflow list fails to load', () => {
    mockUseEmbeddable.mockReturnValue({ workflows: [], isLoading: false, isError: true, error: new Error('x') })
    render(<EmbedWorkflowDialog isOpen onClose={vi.fn()} />)
    expect(screen.getByText(/could not load workflows/i)).toBeInTheDocument()
  })

  it('previews the copy and embeds a plain workflow on confirm', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    withWorkflows()
    resolveDefinition({
      nodes: [
        { id: 'n1', type: 'script', parameters: {} },
        { id: 'n2', type: 'script', parameters: {} },
      ],
      edges: [{ from: 'n1', to: 'n2' }],
      triggers: [],
    })
    render(<EmbedWorkflowDialog isOpen onClose={onClose} projectId="project-1" currentWorkflowId="self" />)

    await selectAlpha(user)
    expect(await screen.findByText(/will be copied/i)).toBeInTheDocument()

    const embed = screen.getByRole('button', { name: 'Embed workflow' })
    expect(embed).toBeEnabled()
    await user.click(embed)

    expect(mocks.insertEmbeddedGraph).toHaveBeenCalledTimes(1)
    expect(mocks.showSuccess).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('allows embed and shows an info notice when the source contains a sub-workflow step', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    withWorkflows()
    resolveDefinition({
      nodes: [{ id: 'n1', type: 'sub_workflow', parameters: { workflow_id: 'x', trigger_node_id: 'y' } }],
      edges: [],
      triggers: [],
    })
    render(<EmbedWorkflowDialog isOpen onClose={onClose} projectId="project-1" currentWorkflowId="self" />)

    await selectAlpha(user)
    // informational, not a block: the copied reference still calls the same child workflow
    expect(await screen.findByText(/call the same child workflows/i)).toBeInTheDocument()
    const embed = screen.getByRole('button', { name: 'Embed workflow' })
    expect(embed).toBeEnabled()
    await user.click(embed)
    expect(mocks.insertEmbeddedGraph).toHaveBeenCalledTimes(1)
    expect(mocks.showSuccess).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('blocks embed and warns when the source references credentials/integrations', async () => {
    const user = userEvent.setup()
    withWorkflows()
    resolveDefinition({
      nodes: [{ id: 'n1', type: 'agentic', parameters: { credential_id: 'cred-1' } }],
      edges: [],
      triggers: [],
    })
    render(<EmbedWorkflowDialog isOpen onClose={vi.fn()} projectId="project-1" currentWorkflowId="self" />)

    await selectAlpha(user)
    expect(await screen.findByText(/references credentials or integrations/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Embed workflow' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('blocks embed and warns when a copied step references the workflow being edited', async () => {
    const user = userEvent.setup()
    withWorkflows()
    resolveDefinition({
      nodes: [{ id: 'n1', type: 'sub_workflow', parameters: { workflow_id: 'self', trigger_node_id: 'y' } }],
      edges: [],
      triggers: [],
    })
    render(<EmbedWorkflowDialog isOpen onClose={vi.fn()} projectId="project-1" currentWorkflowId="self" />)

    await selectAlpha(user)
    expect(await screen.findByText(/references the workflow you're editing/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Embed workflow' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations', async () => {
    withWorkflows()
    const { container } = render(
      <EmbedWorkflowDialog isOpen onClose={vi.fn()} projectId="project-1" currentWorkflowId="self" />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ignores a stale version fetch when the user re-picks before it resolves', async () => {
    const user = userEvent.setup()
    mockUseEmbeddable.mockReturnValue({
      workflows: [
        { id: 'wf-a', name: 'Alpha', published_version_number: 1 },
        { id: 'wf-b', name: 'Beta', published_version_number: 1 },
      ] as never,
      isLoading: false,
      isError: false,
      error: null,
    })

    let resolveAlpha: (value: unknown) => void = () => {}
    const alphaPending = new Promise((resolve) => {
      resolveAlpha = resolve
    })
    mocks.get.mockReturnValueOnce(alphaPending).mockResolvedValueOnce({
      data: { workflow_definition: { nodes: [{ id: 'b1', type: 'script', parameters: {} }], edges: [], triggers: [] } },
      error: undefined,
    })

    render(<EmbedWorkflowDialog isOpen onClose={vi.fn()} projectId="project-1" currentWorkflowId="self" />)

    await user.click(screen.getByRole('button', { name: 'Alpha' })) // request 1 (pending)
    await user.click(screen.getByRole('button', { name: 'Beta' })) // request 2 (resolves, supersedes)
    expect(await screen.findByText(/will be copied/i)).toBeInTheDocument()

    // Alpha's late response carries a sub-workflow node; the guard must ignore it.
    await act(async () => {
      resolveAlpha({
        data: {
          workflow_definition: {
            nodes: [{ id: 'a1', type: 'sub_workflow', parameters: { workflow_id: 'x', trigger_node_id: 'y' } }],
            edges: [],
            triggers: [],
          },
        },
        error: undefined,
      })
      await Promise.resolve()
    })

    expect(screen.queryByText(/call the same child workflows/i)).not.toBeInTheDocument()
    expect(screen.getByText(/will be copied/i)).toBeInTheDocument()
  })
})
