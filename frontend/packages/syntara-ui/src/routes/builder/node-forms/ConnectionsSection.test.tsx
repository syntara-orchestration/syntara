import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { useAllCredentials } from '../components/useAllCredentials'

import { ConnectionsSection } from './ConnectionsSection'
import type { IntegrationConnection } from './ConnectionsSection'
import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'

vi.mock('../../../client', () => ({
  credentialsClient: { useQuery: vi.fn() },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// CredentialSelector fetches its credential list via this hook (see useAllCredentials.test.tsx
// for its own pagination coverage) — mocking it keeps these tests synchronous.
vi.mock('../components/useAllCredentials', () => ({
  useAllCredentials: vi.fn(),
}))

vi.mock('../../configuration/credentials/form/CredentialFormModal', () => ({
  CredentialFormModal: ({
    isOpen,
    onClose,
    onCreated,
    preSelectedTypeId,
    defaultProjectId,
  }: {
    isOpen: boolean
    onClose: () => void
    onCreated?: (id: string) => void
    preSelectedTypeId?: string
    defaultProjectId?: string
  }) =>
    isOpen ? (
      <div
        data-testid="credential-form-modal"
        data-pre-selected-type-id={preSelectedTypeId}
        data-default-project-id={defaultProjectId}
      >
        <button onClick={onClose}>Close modal</button>
        <button onClick={() => onCreated?.('new-cred-id')}>Simulate create</button>
      </div>
    ) : null,
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const integrations: IntegrationWithTools[] = [
  {
    id: 'int-1',
    name: 'Primary MCP Server',
    discovered_tools: [
      { id: 'tool-1', name: 'tool-1' },
      { id: 'tool-2', name: 'tool-2' },
    ],
  },
  {
    id: 'int-2',
    name: 'Dev MCP Server',
    discovered_tools: [{ id: 'tool-3', name: 'tool-3' }],
  },
]

const noCredentials = {
  data: { resources: [] },
  isPending: false,
  isError: false,
  refetch: vi.fn(),
}

beforeEach(() => {
  vi.mocked(credentialsClient.useQuery).mockReturnValue(noCredentials as ReturnType<typeof credentialsClient.useQuery>)
  vi.mocked(useAllCredentials).mockReturnValue({
    credentials: [],
    isLoading: false,
    error: null,
    refetch: vi.fn() as unknown as ReturnType<typeof useAllCredentials>['refetch'],
  })
})

const NONE: ToolSelection = { strategy: 'NONE' }
const ALL: ToolSelection = { strategy: 'ALL' }
const selected = (...ids: string[]): ToolSelection => ({ strategy: 'SELECTED', toolIds: ids })

function renderSection(
  toolSelection: ToolSelection,
  integrationConnections: IntegrationConnection[] = [],
  onChange = vi.fn(),
  projectId?: string
) {
  return render(
    <ConnectionsSection
      integrations={integrations}
      toolSelection={toolSelection}
      integrationConnections={integrationConnections}
      onConnectionChange={onChange}
      projectId={projectId}
    />,
    { wrapper }
  )
}

describe('ConnectionsSection', () => {
  it('renders nothing when strategy is NONE', () => {
    const { container } = renderSection(NONE)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows all integrations with tools when strategy is ALL', () => {
    renderSection(ALL)

    expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
    expect(screen.getByText('Dev MCP Server')).toBeInTheDocument()
  })

  it('shows full tool count per integration when strategy is ALL', () => {
    renderSection(ALL)

    expect(screen.getByText(/2 tools/)).toBeInTheDocument()
    expect(screen.getByText(/1 tool/)).toBeInTheDocument()
  })

  it('shows only the integration whose tool is selected (SELECTED strategy)', () => {
    renderSection(selected('tool-1'))

    expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
    expect(screen.queryByText('Dev MCP Server')).not.toBeInTheDocument()
  })

  it('shows both integrations when tools from both are selected', () => {
    renderSection(selected('tool-1', 'tool-3'))

    expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
    expect(screen.getByText('Dev MCP Server')).toBeInTheDocument()
  })

  it('shows correct tool count when all tools in an integration are selected', () => {
    renderSection(selected('tool-1', 'tool-2'))

    expect(screen.getByText(/2 tools/)).toBeInTheDocument()
  })

  it('shows 0 of N connected when no credentials are set (SELECTED)', () => {
    renderSection(selected('tool-1', 'tool-3'))

    expect(screen.getByRole('button', { name: /connections/i })).toBeInTheDocument()
    expect(screen.getByText('0 of 2 connected')).toBeInTheDocument()
  })

  it('shows 0 of N connected when no credentials are set (ALL)', () => {
    renderSection(ALL)

    expect(screen.getByRole('button', { name: /connections/i })).toBeInTheDocument()
    expect(screen.getByText('0 of 2 connected')).toBeInTheDocument()
  })

  it('shows N of N connected when all credentials are set', () => {
    renderSection(selected('tool-1', 'tool-3'), [
      { integration_id: 'int-1', credential_id: 'cred-1' },
      { integration_id: 'int-2', credential_id: 'cred-2' },
    ])

    expect(screen.getByRole('button', { name: /connections/i })).toBeInTheDocument()
    expect(screen.getByText('2 of 2 connected')).toBeInTheDocument()
  })

  describe('collapsed/expanded row behavior', () => {
    it('does not show CredentialSelector by default (collapsed)', () => {
      renderSection(ALL)

      expect(
        screen.queryByRole('button', { name: 'Execution credential for Primary MCP Server' })
      ).not.toBeInTheDocument()
    })

    it('shows "Set up connection" for unconnected rows', () => {
      renderSection(ALL)

      expect(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i })).toBeInTheDocument()
    })

    it('shows "Change" for connected rows', () => {
      renderSection(ALL, [{ integration_id: 'int-1', credential_id: 'cred-1' }])

      expect(screen.getByRole('button', { name: /change credential for Primary MCP Server/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /set up connection for Dev MCP Server/i })).toBeInTheDocument()
    })

    it('reveals CredentialSelector when "Set up connection" is clicked', async () => {
      const user = userEvent.setup()
      renderSection(ALL)

      await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))

      expect(screen.getByRole('button', { name: 'Execution credential for Primary MCP Server' })).toBeInTheDocument()
    })

    it('collapses current row and expands new row when a second row is opened', async () => {
      const user = userEvent.setup()
      renderSection(selected('tool-1', 'tool-3'))

      await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))
      expect(screen.getByRole('button', { name: 'Execution credential for Primary MCP Server' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /set up connection for Dev MCP Server/i }))

      // Only the newly opened row's selector is visible
      expect(
        screen.queryByRole('button', { name: 'Execution credential for Primary MCP Server' })
      ).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Execution credential for Dev MCP Server' })).toBeInTheDocument()
    })

    it('collapses without calling onConnectionChange when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      renderSection(ALL, [], onChange)

      await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))
      await user.click(screen.getByRole('button', { name: /cancel setting up connection for Primary MCP Server/i }))

      expect(onChange).not.toHaveBeenCalled()
      expect(
        screen.queryByRole('button', { name: 'Execution credential for Primary MCP Server' })
      ).not.toBeInTheDocument()
    })

    it('removes a credential and collapses when Remove is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      renderSection(selected('tool-1'), [{ integration_id: 'int-1', credential_id: 'cred-1' }], onChange)

      await user.click(screen.getByRole('button', { name: /change credential for Primary MCP Server/i }))
      await user.click(screen.getByRole('button', { name: /remove credential for Primary MCP Server/i }))

      expect(onChange).toHaveBeenCalledWith([])
      expect(
        screen.queryByRole('button', { name: 'Execution credential for Primary MCP Server' })
      ).not.toBeInTheDocument()
    })
  })

  it('has no accessibility violations (SELECTED)', async () => {
    const { container } = renderSection(selected('tool-1'))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations (ALL)', async () => {
    const { container } = renderSection(ALL)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when a row is expanded', async () => {
    const user = userEvent.setup()
    const { container } = renderSection(ALL)

    await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('inline credential creation', () => {
    it('shows "Create new credential" option in the credential dropdown', async () => {
      const user = userEvent.setup()
      renderSection(ALL)

      await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))
      await user.click(screen.getByRole('button', { name: 'Execution credential for Primary MCP Server' }))

      expect(screen.getByText('Create new credential')).toBeInTheDocument()
    })

    it('passes projectId to filter credentials', async () => {
      const user = userEvent.setup()
      renderSection(ALL, [], vi.fn(), 'project-42')

      await user.click(screen.getByRole('button', { name: /set up connection for Primary MCP Server/i }))

      expect(useAllCredentials).toHaveBeenCalledWith({ projectId: 'project-42' })
    })
  })
})
