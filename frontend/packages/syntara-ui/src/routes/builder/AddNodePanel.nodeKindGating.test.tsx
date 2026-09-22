import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { AddNodePanel } from './AddNodePanel'

const { mockNodeRegistryGetAll, mockNodeRegistryGet, mockNodeKindByKind } = vi.hoisted(() => ({
  mockNodeRegistryGetAll: vi.fn(),
  mockNodeRegistryGet: vi.fn(),
  mockNodeKindByKind: { current: new Map<string, unknown>() },
}))

vi.mock('./registry/NodeRegistry', () => ({
  NodeRegistry: {
    getAll: mockNodeRegistryGetAll,
    get: mockNodeRegistryGet,
  },
}))

vi.mock('../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    query: { isPending: false },
    nodeKinds: [],
    nodeKindByKind: mockNodeKindByKind.current,
    disabledKinds: new Set<string>(),
  }),
}))

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    enabled: true,
    switchable: true,
    deniable_actions: ['write', 'execute'],
    can_write: true,
    ...overrides,
  }
}

function setNodeKinds(...kinds: NodeKind[]) {
  mockNodeKindByKind.current = new Map(kinds.map((entry) => [entry.kind, entry]))
}

const scriptEntry = {
  id: 'action-script',
  label: 'Script',
  icon: () => <div>ScriptIcon</div>,
  category: 'task',
  order: 10,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

const apiEntry = {
  id: 'action-api',
  label: 'REST API',
  icon: () => <div>ApiIcon</div>,
  category: 'task',
  order: 20,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

const agentEntry = {
  id: 'agent',
  label: 'Task Agent',
  icon: () => <div>AgentIcon</div>,
  category: 'task',
  order: 30,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

describe('AddNodePanel node-kind gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNodeRegistryGetAll.mockReturnValue([scriptEntry, apiEntry, agentEntry])
    mockNodeRegistryGet.mockImplementation((id: string) =>
      [scriptEntry, apiEntry, agentEntry].find((entry) => entry.id === id)
    )
    setNodeKinds(kind({ kind: 'script' }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
  })

  it('lists every kind that is enabled and writable', () => {
    render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Task Agent' })).toBeInTheDocument()
  })

  it('hides a kind that is switched off platform-wide', () => {
    setNodeKinds(kind({ kind: 'script' }), kind({ kind: 'http_request', enabled: false }), kind({ kind: 'agentic' }))

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'REST API' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
  })

  it('keeps a denied kind listed but marks it disabled', () => {
    setNodeKinds(kind({ kind: 'script', can_write: false }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Script' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'REST API' })).not.toHaveAttribute('aria-disabled')
  })

  it('does not add a node when a denied palette entry is activated', async () => {
    setNodeKinds(kind({ kind: 'script', can_write: false }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
    const onSelectNode = vi.fn()
    const user = userEvent.setup()

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={onSelectNode} />)
    await user.click(screen.getByRole('button', { name: 'Script' }))

    expect(onSelectNode).not.toHaveBeenCalled()
  })

  it('still adds a node for an allowed palette entry', async () => {
    setNodeKinds(kind({ kind: 'script', can_write: false }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
    const onSelectNode = vi.fn()
    const user = userEvent.setup()

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={onSelectNode} />)
    await user.click(screen.getByRole('button', { name: 'REST API' }))

    expect(onSelectNode).toHaveBeenCalledWith('action-api', null)
  })

  it('explains the denial in a tooltip on hover', async () => {
    setNodeKinds(kind({ kind: 'script', can_write: false }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
    const user = userEvent.setup()

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)
    await user.hover(screen.getByRole('button', { name: 'Script' }))

    expect(await screen.findByText('You are not allowed to add script nodes')).toBeInTheDocument()
  })

  it('renders the full palette while the node-kind registry is still empty', () => {
    setNodeKinds()

    render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).toBeInTheDocument()
  })
})
