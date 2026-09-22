import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { NodeKind } from '../../../../hooks/useNodeKindsQuery'

import { NodeKindsTab } from './NodeKindsTab'
import { nodeKindSwitchTooltip } from './nodeKindSwitchTooltip'

const { mockNodeKinds, mockSetEnabled, mockShowError, mockShowSuccess, mockInvalidateQueries, mockQueryState } =
  vi.hoisted(() => ({
    mockNodeKinds: { current: [] as unknown[] },
    mockSetEnabled: vi.fn(),
    mockShowError: vi.fn(),
    mockShowSuccess: vi.fn(),
    mockInvalidateQueries: vi.fn(),
    mockQueryState: { current: null as ReactNode },
  }))

vi.mock('../../../../hooks/useNodeKindsQuery', () => ({
  NODE_KINDS_QUERY_PATH: '/node_kinds',
  useNodeKindsQuery: () => ({
    query: { refetch: vi.fn() },
    nodeKinds: mockNodeKinds.current,
    nodeKindByKind: new Map(),
    disabledKinds: new Set<string>(),
  }),
  useSetNodeKindEnabledMutation: () => ({ mutateAsync: mockSetEnabled }),
}))

vi.mock('../../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError, showSuccess: mockShowSuccess }),
}))

vi.mock('@tanstack/react-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}))

vi.mock('../../../../components/states/useQueryState', () => ({
  useQueryState: () => mockQueryState.current,
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

const scriptKind = kind({ kind: 'script' })
const agenticKind = kind({ kind: 'agentic', enabled: false })
const conditionKind = kind({
  kind: 'condition',
  category: 'flow_control',
  switchable: false,
  deniable_actions: [],
})
const manualTrigger = kind({ kind: 'manual_trigger', category: 'trigger', deniable_actions: ['write'] })

function setNodeKinds(...kinds: NodeKind[]) {
  mockNodeKinds.current = kinds
}

describe('NodeKindsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryState.current = null
    mockSetEnabled.mockResolvedValue({})
    mockInvalidateQueries.mockResolvedValue(undefined)
    setNodeKinds(scriptKind, agenticKind, conditionKind, manualTrigger)
  })

  it('lists every node kind with its category', () => {
    render(<NodeKindsTab canWrite />)

    expect(screen.getByRole('grid', { name: 'Node kinds' })).toBeInTheDocument()
    expect(screen.getByText('script')).toBeInTheDocument()
    expect(screen.getByText('manual_trigger')).toBeInTheDocument()
    expect(screen.getByText('Flow control')).toBeInTheDocument()
  })

  it('reflects the kill-switch state in each switch', () => {
    render(<NodeKindsTab canWrite />)

    expect(screen.getByRole('switch', { name: 'Enable script nodes' })).toBeChecked()
    expect(screen.getByRole('switch', { name: 'Enable agentic nodes' })).not.toBeChecked()
  })

  it('shows which actions may be denied for each kind', () => {
    render(<NodeKindsTab canWrite />)

    expect(screen.getAllByText('Execute').length).toBeGreaterThan(0)
    expect(screen.getByText('Never denied')).toBeInTheDocument()
  })

  it('calls the kill-switch endpoint and reports success', async () => {
    const user = userEvent.setup()
    render(<NodeKindsTab canWrite />)

    await user.click(screen.getByRole('switch', { name: 'Enable script nodes' }))

    await waitFor(() => {
      expect(mockSetEnabled).toHaveBeenCalledWith({ params: { path: { kind: 'script' } }, body: { enabled: false } })
    })
    await waitFor(() => {
      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Disabled script nodes' })
    })
  })

  it('re-enables a disabled kind', async () => {
    const user = userEvent.setup()
    render(<NodeKindsTab canWrite />)

    await user.click(screen.getByRole('switch', { name: 'Enable agentic nodes' }))

    await waitFor(() => {
      expect(mockSetEnabled).toHaveBeenCalledWith({ params: { path: { kind: 'agentic' } }, body: { enabled: true } })
    })
  })

  it('reports a failed switch as an error alert', async () => {
    mockSetEnabled.mockRejectedValue({ detail: 'Node kind cannot be switched off' })
    const user = userEvent.setup()
    render(<NodeKindsTab canWrite />)

    await user.click(screen.getByRole('switch', { name: 'Enable script nodes' }))

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Failed to disable script nodes',
        description: 'Node kind cannot be switched off',
      })
    })
  })

  it('disables the switch for a kind that cannot be switched off', () => {
    render(<NodeKindsTab canWrite />)

    expect(screen.getByRole('switch', { name: 'Enable condition nodes' })).toBeDisabled()
  })

  it('disables every switch without setting:write', () => {
    render(<NodeKindsTab canWrite={false} />)

    expect(screen.getByRole('switch', { name: 'Enable script nodes' })).toBeDisabled()
    expect(mockSetEnabled).not.toHaveBeenCalled()
  })

  it('renders the query error state instead of the table', () => {
    mockQueryState.current = <div>Error loading node kinds</div>

    render(<NodeKindsTab canWrite />)

    expect(screen.getByText('Error loading node kinds')).toBeInTheDocument()
    expect(screen.queryByRole('grid', { name: 'Node kinds' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<NodeKindsTab canWrite />)

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('nodeKindSwitchTooltip', () => {
  it('explains that flow control kinds cannot be switched off', () => {
    expect(nodeKindSwitchTooltip(conditionKind, true)).toContain('cannot be switched off')
  })

  it('explains the missing permission', () => {
    expect(nodeKindSwitchTooltip(scriptKind, false)).toContain('setting:write')
  })

  it('returns null when the switch is usable', () => {
    expect(nodeKindSwitchTooltip(scriptKind, true)).toBeNull()
  })
})
