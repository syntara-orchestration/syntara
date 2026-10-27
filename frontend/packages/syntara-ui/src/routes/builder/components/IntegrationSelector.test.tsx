import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationStatusEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'

import { IntegrationSelector } from './IntegrationSelector'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

const mockIntegrations = [
  {
    id: 'int-1',
    name: 'Primary MCP Server',
    integration_type: 'mcp_server',
    validation_status: IntegrationStatusEnum.AVAILABLE,
    enabled: true,
    configuration: { integration_type: 'mcp_server', base_url: 'https://mcp.example.com' },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'int-2',
    name: 'Dev MCP Server',
    integration_type: 'mcp_server',
    validation_status: IntegrationStatusEnum.ERROR,
    enabled: true,
    configuration: { integration_type: 'mcp_server', base_url: 'https://dev.example.com' },
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
  },
] as unknown as IntegrationRead[]

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

function mockQuerySuccess(resources = mockIntegrations) {
  vi.mocked(integrationsClient.useQuery).mockReturnValue({
    data: { resources, next: null, prev: null },
    isPending: false,
    isError: false,
    refetch: vi.fn(),
  } as ReturnType<typeof integrationsClient.useQuery>)
}

function mockQueryLoading() {
  vi.mocked(integrationsClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: true,
    isError: false,
    refetch: vi.fn(),
  } as ReturnType<typeof integrationsClient.useQuery>)
}

function mockQueryError() {
  vi.mocked(integrationsClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: true,
    refetch: vi.fn(),
  } as ReturnType<typeof integrationsClient.useQuery>)
}

function renderSelector(props: Partial<Parameters<typeof IntegrationSelector>[0]> = {}) {
  const onChange = vi.fn()
  render(<IntegrationSelector onChange={onChange} {...props} />, { wrapper })
  return { onChange }
}

describe('IntegrationSelector', () => {
  beforeEach(() => {
    mockQuerySuccess()
  })

  it('renders with default label', () => {
    renderSelector()
    expect(screen.getByRole('button', { name: /MCP server integration/i })).toBeInTheDocument()
  })

  it('renders custom label', () => {
    renderSelector({ label: 'Custom Label' })
    expect(screen.getByRole('button', { name: /Custom Label/i })).toBeInTheDocument()
  })

  it('shows spinner while loading', () => {
    mockQueryLoading()
    renderSelector()
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByText('Loading integrations...')).toBeInTheDocument()
  })

  it('shows integrations in dropdown when opened', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    expect(screen.getByRole('option', { name: /Primary MCP Server/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Dev MCP Server/i })).toBeInTheDocument()
  })

  it('shows no integration option in dropdown', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    expect(screen.getByRole('option', { name: /No integration/i })).toBeInTheDocument()
  })

  it('shows status badges for integrations', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    expect(screen.getByText('Available')).toBeInTheDocument()
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('shows outline status badges for all integration validation states', async () => {
    mockQuerySuccess([
      ...mockIntegrations,
      {
        id: 'int-3',
        name: 'Pending MCP Server',
        integration_type: 'mcp_server',
        validation_status: IntegrationStatusEnum.VALIDATING,
        enabled: true,
        configuration: { integration_type: 'mcp_server', base_url: 'https://pending.example.com' },
        created_at: '2024-03-01T00:00:00Z',
        updated_at: '2024-03-01T00:00:00Z',
      },
      {
        id: 'int-4',
        name: 'Unknown MCP Server',
        integration_type: 'mcp_server',
        validation_status: IntegrationStatusEnum.UNKNOWN,
        enabled: true,
        configuration: { integration_type: 'mcp_server', base_url: 'https://unknown.example.com' },
        created_at: '2024-04-01T00:00:00Z',
        updated_at: '2024-04-01T00:00:00Z',
      },
    ] as unknown as IntegrationRead[])
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    expect(screen.getByText('Available', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getByText('Error', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getByText('Validating', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getByText('Unknown', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
  })

  it('calls onChange with integration id when selection is made', async () => {
    const user = userEvent.setup()
    const { onChange } = renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))
    await user.click(screen.getByRole('option', { name: /Primary MCP Server/i }))

    expect(onChange).toHaveBeenCalledWith('int-1')
  })

  it('calls onChange with undefined when "no integration" option is selected', async () => {
    const user = userEvent.setup()
    const { onChange } = renderSelector({ value: 'int-1' })

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))
    await user.click(screen.getByRole('option', { name: /No integration/i }))

    expect(onChange).toHaveBeenCalledWith(undefined)
  })

  it('shows selected integration name as visible toggle text', () => {
    renderSelector({ value: 'int-2' })
    // The button's aria-label is the field label; the selected name is shown as visual text
    expect(screen.getByRole('button', { name: /MCP server integration/i })).toHaveTextContent('Dev MCP Server')
  })

  it('shows retry button when API call fails', () => {
    mockQueryError()
    renderSelector()
    expect(screen.getByRole('button', { name: /Retry loading integrations/i })).toBeInTheDocument()
  })

  it('shows empty state when no integrations are returned', async () => {
    mockQuerySuccess([])
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    await waitFor(() => {
      expect(screen.getByText('No MCP server integrations available')).toBeInTheDocument()
    })
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = render(<IntegrationSelector onChange={vi.fn()} />, { wrapper })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with dropdown open', async () => {
    const user = userEvent.setup()
    const { container } = render(<IntegrationSelector onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /Primary MCP Server/i })).toBeInTheDocument()
    })

    expect(await axe(container)).toHaveNoViolations()
  })

  it('passes project_id to the integrations query when projectId is provided', () => {
    renderSelector({ projectId: 'proj-123' })
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'mcp_server', enabled: true, project_id: 'proj-123' },
      },
    })
  })

  it('does not include project_id in the query when projectId is omitted', () => {
    renderSelector()
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'mcp_server', enabled: true },
      },
    })
  })

  it('renders only project-scoped integrations when projectId filters the result set', async () => {
    const projectScopedIntegrations = [mockIntegrations[0]]
    mockQuerySuccess(projectScopedIntegrations)
    const user = userEvent.setup()
    renderSelector({ projectId: 'proj-123' })

    await user.click(screen.getByRole('button', { name: /MCP server integration/i }))

    expect(screen.getByRole('option', { name: /Primary MCP Server/i })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Dev MCP Server/i })).not.toBeInTheDocument()
  })
})
