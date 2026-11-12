import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { AddStepPanel } from './AddStepPanel'

const { mockStepRegistryGetAll, mockStepRegistryGet, mockNodeKindByKind, mockIsUnavailable } = vi.hoisted(() => ({
  mockStepRegistryGetAll: vi.fn(),
  mockStepRegistryGet: vi.fn(),
  mockNodeKindByKind: { current: new Map<string, unknown>() },
  mockIsUnavailable: { current: false },
}))

vi.mock('./registry/StepRegistry', () => ({
  StepRegistry: {
    getAll: mockStepRegistryGetAll,
    get: mockStepRegistryGet,
  },
}))

vi.mock('../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    query: { isPending: false },
    nodeKinds: [],
    nodeKindByKind: mockNodeKindByKind.current,
    isUnavailable: mockIsUnavailable.current,
  }),
}))

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    can_write: true,
    blocked_by: null,
    ...overrides,
  }
}

function setNodeKinds(...kinds: NodeKind[]) {
  mockNodeKindByKind.current = new Map(kinds.map((entry) => [entry.kind, entry]))
}

const scriptDeny = {
  kind: 'script',
  label: 'Script',
  reason: 'explicit_deny',
  policy: 'no-scripts-in-payments',
  scope: 'project',
  project: 'payments',
} as const

const scriptEntry = {
  id: 'script',
  label: 'Script',
  icon: () => <div>ScriptIcon</div>,
  category: 'task',
  order: 10,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

const apiEntry = {
  id: 'http_request',
  label: 'REST API',
  icon: () => <div>ApiIcon</div>,
  category: 'task',
  order: 20,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

const agentEntry = {
  id: 'agentic',
  label: 'Task Agent',
  icon: () => <div>AgentIcon</div>,
  category: 'task',
  order: 30,
  formComponent: () => null,
  onSubmit: vi.fn(),
}

describe('AddStepPanel step-type gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStepRegistryGetAll.mockReturnValue([scriptEntry, apiEntry, agentEntry])
    mockStepRegistryGet.mockImplementation((id: string) =>
      [scriptEntry, apiEntry, agentEntry].find((entry) => entry.id === id)
    )
    mockIsUnavailable.current = false
    setNodeKinds(kind({ kind: 'script' }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
  })

  it('lists every kind the caller may write', () => {
    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Task Agent' })).toBeInTheDocument()
  })

  it('keeps a blocked kind listed but marks it disabled', () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.getByRole('button', { name: 'Script' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'REST API' })).not.toHaveAttribute('aria-disabled')
  })

  it('does not add a step when a blocked palette entry is activated', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const onSelectStep = vi.fn()
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={onSelectStep} projectId="project-1" />)
    await user.click(screen.getByRole('button', { name: 'Script' }))

    expect(onSelectStep).not.toHaveBeenCalled()
  })

  it('still adds a step for an allowed palette entry', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const onSelectStep = vi.fn()
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={onSelectStep} projectId="project-1" />)
    await user.click(screen.getByRole('button', { name: 'REST API' }))

    expect(onSelectStep).toHaveBeenCalledWith('http_request', null)
  })

  it('explains the block in a tooltip naming the policy and scope on hover', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)
    await user.hover(screen.getByRole('button', { name: 'Script' }))

    expect(await screen.findByText('Blocked by no-scripts-in-payments (project payments)')).toBeInTheDocument()
  })

  it('disables every entry instead of claiming everything is allowed when the endpoint fails', () => {
    mockIsUnavailable.current = true

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.getByRole('button', { name: 'Script' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'REST API' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'Task Agent' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('explains a missing allow instead of naming a denying policy', async () => {
    setNodeKinds(
      kind({
        kind: 'script',
        can_write: false,
        blocked_by: {
          kind: 'script',
          label: 'Script',
          reason: 'no_matching_allow',
          policy: null,
          scope: null,
          project: 'payments',
        },
      }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)
    await user.hover(screen.getByRole('button', { name: 'Script' }))

    expect(
      await screen.findByText('No policy grants write permission for Script in project payments')
    ).toBeInTheDocument()
  })
})
