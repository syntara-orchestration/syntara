import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { AddStepPanel } from './AddStepPanel'
import { STEP_TYPE_NO_PROJECT_TOOLTIP, STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP } from './stepTypePaletteGating'

const { mockStepRegistryGetAll, mockStepRegistryGet, mockNodeKindByKind, mockIsUnavailable, mockIsLoading } =
  vi.hoisted(() => ({
    mockStepRegistryGetAll: vi.fn(),
    mockStepRegistryGet: vi.fn(),
    mockNodeKindByKind: { current: new Map<string, unknown>() },
    mockIsUnavailable: { current: false },
    mockIsLoading: { current: false },
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
    isLoading: mockIsLoading.current,
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
    mockIsLoading.current = false
    setNodeKinds(kind({ kind: 'script' }), kind({ kind: 'http_request' }), kind({ kind: 'agentic' }))
  })

  it('lists every kind the caller may write', () => {
    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Task Agent' })).toBeInTheDocument()
  })

  it('hides a blocked kind from the palette by default', () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.queryByRole('button', { name: 'Script' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).not.toHaveAttribute('aria-disabled')
    expect(screen.getByRole('switch', { name: 'Show restricted steps' })).not.toBeChecked()
    expect(screen.getByTestId('add-step-hidden-count')).toHaveTextContent('1 step you cannot add is hidden.')
  })

  it('reveals blocked kinds as padlocked, disabled cards when the switch is on', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)
    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))

    const script = screen.getByRole('button', { name: 'Script' })
    expect(script).toHaveAttribute('aria-disabled', 'true')
    expect(within(script).getByTestId('step-type-lock-icon')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).not.toHaveAttribute('aria-disabled')
    expect(within(screen.getByRole('button', { name: 'REST API' })).queryByTestId('step-type-lock-icon')).toBeNull()
    expect(screen.queryByTestId('add-step-hidden-count')).not.toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
    expect(screen.queryByRole('button', { name: 'Script' })).not.toBeInTheDocument()
  })

  it('does not show the switch when nothing is blocked', () => {
    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.queryByRole('switch', { name: 'Show restricted steps' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('add-step-hidden-count')).not.toBeInTheDocument()
  })

  it('does not add a step when a revealed blocked palette entry is activated', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )
    const onSelectStep = vi.fn()
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={onSelectStep} projectId="project-1" />)
    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
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
    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
    await user.hover(screen.getByRole('button', { name: 'Script' }))

    expect(await screen.findByText('Blocked by no-scripts-in-payments (project payments)')).toBeInTheDocument()
  })

  it('points at the switch when every entry in the list is blocked', async () => {
    setNodeKinds(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request', can_write: false, blocked_by: { ...scriptDeny, kind: 'http_request' } }),
      kind({ kind: 'agentic', can_write: false, blocked_by: { ...scriptDeny, kind: 'agentic' } })
    )
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.queryAllByRole('button', { name: /Script|REST API|Task Agent/ })).toHaveLength(0)
    expect(screen.getByTestId('add-step-all-restricted')).toHaveTextContent('Show restricted steps')
    expect(screen.getByTestId('add-step-hidden-count')).toHaveTextContent('3 steps you cannot add are hidden.')

    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))

    expect(screen.queryByTestId('add-step-all-restricted')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Task Agent' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('disables every entry instead of claiming everything is allowed when the endpoint fails', async () => {
    mockIsUnavailable.current = true
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    // Failing closed keeps every entry listed (disabled) rather than an empty palette.
    expect(screen.getByRole('button', { name: 'Script' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'REST API' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'Task Agent' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('switch', { name: 'Show restricted steps' })).not.toBeInTheDocument()
    expect(screen.getByTestId('add-step-permissions-unavailable')).toHaveTextContent(
      STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
    )

    await user.hover(screen.getByRole('button', { name: 'Script' }))
    expect(await screen.findByRole('tooltip')).toHaveTextContent(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
  })

  it('fails closed when no project is selected instead of allowing everything', async () => {
    // With no project the real hook is disabled and returns an empty registry.
    mockNodeKindByKind.current = new Map()
    const onSelectStep = vi.fn()
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={onSelectStep} projectId={null} />)

    for (const name of ['Script', 'REST API', 'Task Agent']) {
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-disabled', 'true')
    }
    expect(screen.queryByRole('switch', { name: 'Show restricted steps' })).not.toBeInTheDocument()
    expect(screen.getByTestId('add-step-permissions-unavailable')).toHaveTextContent(STEP_TYPE_NO_PROJECT_TOOLTIP)

    await user.click(screen.getByRole('button', { name: 'REST API' }))
    expect(onSelectStep).not.toHaveBeenCalled()

    await user.hover(screen.getByRole('button', { name: 'Script' }))
    expect(await screen.findByRole('tooltip')).toHaveTextContent(STEP_TYPE_NO_PROJECT_TOOLTIP)
  })

  it('fails closed when the project id is omitted', () => {
    mockNodeKindByKind.current = new Map()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Script' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows a loading state instead of disabling every entry while verdicts load', () => {
    mockIsLoading.current = true

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.getByText('Checking step permissions…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Script' })).not.toBeInTheDocument()
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
    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
    await user.hover(screen.getByRole('button', { name: 'Script' }))

    expect(
      await screen.findByText('No policy grants write permission for Script in project payments')
    ).toBeInTheDocument()
  })
})

describe('AddStepPanel step-type gating for container entries', () => {
  const logicEntry = {
    id: 'logic',
    label: 'Logic',
    icon: () => <div>LogicIcon</div>,
    category: 'flow_control',
    order: 40,
    formComponent: () => null,
    onSubmit: vi.fn(),
    selectionTitle: 'Select logic',
    subtypes: [
      { id: 'condition', label: 'Condition', icon: () => <div>ConditionIcon</div>, order: 1 },
      { id: 'loop', label: 'Loop', icon: () => <div>LoopIcon</div>, order: 2 },
    ],
  }
  const loopDeny = { ...scriptDeny, kind: 'loop', label: 'Loop', policy: 'no-loops' }

  beforeEach(() => {
    vi.clearAllMocks()
    mockStepRegistryGetAll.mockReturnValue([apiEntry, logicEntry])
    mockStepRegistryGet.mockImplementation((id: string) => [apiEntry, logicEntry].find((entry) => entry.id === id))
    mockIsUnavailable.current = false
    mockIsLoading.current = false
  })

  it('keeps a container with some allowed subtypes and hides its blocked subtypes by default', async () => {
    setNodeKinds(
      kind({ kind: 'http_request' }),
      kind({ kind: 'condition' }),
      kind({ kind: 'loop', can_write: false, blocked_by: loopDeny })
    )
    const onSelectStep = vi.fn()
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={onSelectStep} projectId="project-1" />)

    // Top level: nothing blocked, so no switch.
    expect(screen.queryByRole('switch', { name: 'Show restricted steps' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Logic' }))

    expect(screen.getByRole('button', { name: 'Condition' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Loop' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
    const loop = screen.getByRole('button', { name: 'Loop' })
    expect(loop).toHaveAttribute('aria-disabled', 'true')
    expect(within(loop).getByTestId('step-type-lock-icon')).toBeInTheDocument()

    await user.click(loop)
    expect(onSelectStep).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Condition' }))
    expect(onSelectStep).toHaveBeenCalledWith('logic', 'condition')
  })

  it('hides a container whose subtypes are all blocked, and reveals it padlocked', async () => {
    setNodeKinds(
      kind({ kind: 'http_request' }),
      kind({ kind: 'condition', can_write: false, blocked_by: { ...loopDeny, kind: 'condition' } }),
      kind({ kind: 'loop', can_write: false, blocked_by: loopDeny })
    )
    const user = userEvent.setup()

    render(<AddStepPanel onClose={vi.fn()} onSelectStep={vi.fn()} projectId="project-1" />)

    expect(screen.queryByRole('button', { name: 'Logic' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'REST API' })).toBeInTheDocument()

    await user.click(screen.getByRole('switch', { name: 'Show restricted steps' }))
    const logic = screen.getByRole('button', { name: 'Logic' })
    expect(logic).toHaveAttribute('aria-disabled', 'true')
    expect(within(logic).getByTestId('step-type-lock-icon')).toBeInTheDocument()

    await user.click(logic)
    expect(screen.queryByRole('button', { name: 'Condition' })).not.toBeInTheDocument()
  })
})
