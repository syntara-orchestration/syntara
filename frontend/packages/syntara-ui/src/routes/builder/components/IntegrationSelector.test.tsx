import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationStatusEnum, IntegrationTypeEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { IntegrationSelector, type IntegrationSelectorProps } from './IntegrationSelector'

const { integrationsQuery } = vi.hoisted(() => ({ integrationsQuery: vi.fn() }))
vi.mock('./useAllIntegrations', () => ({ useAllIntegrations: integrationsQuery }))

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
  integrationsQuery.mockReturnValue({
    data: resources,
    isPending: false,
    isError: false,
    refetch: vi.fn(),
  })
}

function mockQueryLoading() {
  integrationsQuery.mockReturnValue({
    data: undefined,
    isPending: true,
    isError: false,
    refetch: vi.fn(),
  })
}

function mockQueryError() {
  integrationsQuery.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: true,
    refetch: vi.fn(),
  })
}

function renderSelector(props: Partial<Parameters<typeof IntegrationSelector>[0]> = {}) {
  const onChange = vi.fn()
  render(<IntegrationSelector onChange={onChange} {...props} />, { wrapper })
  return { onChange }
}

describe('IntegrationSelector', () => {
  it('uses the Kafka API and workflow project scope for Kafka selection', () => {
    mockQuerySuccess([])
    renderSelector({ integrationType: IntegrationTypeEnum.KAFKA, projectId: 'project-id', label: 'Kafka integration' })
    expect(integrationsQuery).toHaveBeenCalledWith(IntegrationTypeEnum.KAFKA, 'project-id')
  })

  it('shows Kafka broker addresses and availability in the integration menu', async () => {
    const kafkaIntegration = {
      id: 'kafka-integration',
      name: 'Kafka Cluster (Demo)',
      integration_type: IntegrationTypeEnum.KAFKA,
      validation_status: IntegrationStatusEnum.AVAILABLE,
      configuration: {
        integration_type: IntegrationTypeEnum.KAFKA,
        bootstrap_servers: ['broker-1.example.invalid:9093', 'broker-2.example.invalid:9093'],
        security_protocol: 'SASL_SSL',
      },
    } satisfies IntegrationsAPI.components['schemas']['KafkaIntegrationRead']
    integrationsQuery.mockReturnValue({ data: [kafkaIntegration], isPending: false, isError: false })
    const user = userEvent.setup()
    const { container } = render(
      <IntegrationSelector
        integrationType={IntegrationTypeEnum.KAFKA}
        label="Integration"
        isRequired
        placeholder="Select a Kafka integration"
        onChange={vi.fn()}
      />,
      { wrapper }
    )

    expect(screen.getByRole('button', { name: 'Integration' })).toHaveTextContent('Select a Kafka integration')
    await user.click(screen.getByRole('button', { name: 'Integration' }))
    expect(screen.getByRole('option', { name: /Kafka Cluster \(Demo\)/ })).toHaveTextContent('Available')
    expect(screen.getByText('broker-1.example.invalid:9093, broker-2.example.invalid:9093')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
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
    expect(screen.getByRole('button')).toHaveTextContent('Select an MCP server integration...')
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText('Loading integrations...')).not.toBeInTheDocument()
  })

  it('keeps the Kafka prompt stable through initial loading and cached refreshes', async () => {
    const option = {
      id: 'kafka-id',
      name: 'Orders Kafka',
      integration_type: IntegrationTypeEnum.KAFKA,
      enabled: true,
      configuration: { integration_type: IntegrationTypeEnum.KAFKA, bootstrap_servers: ['broker.example.com:9093'] },
    } satisfies IntegrationsAPI.components['schemas']['KafkaIntegrationRead']
    const onChange = vi.fn()
    const props: IntegrationSelectorProps = {
      integrationType: IntegrationTypeEnum.KAFKA,
      label: 'Integration',
      placeholder: 'Select a Kafka integration',
      onChange,
    }
    mockQueryLoading()
    const { rerender } = render(<IntegrationSelector {...props} />, { wrapper })
    const toggle = screen.getByRole('button', { name: 'Integration' })
    expect(toggle).toHaveTextContent('Select a Kafka integration')
    expect(toggle).toHaveAttribute('aria-busy', 'true')
    expect(toggle).toBeDisabled()

    integrationsQuery.mockReturnValue({ data: [option], isPending: false, isError: false })
    rerender(<IntegrationSelector {...props} />)
    expect(toggle).toHaveTextContent('Select a Kafka integration')
    expect(toggle).not.toHaveAttribute('aria-busy', 'true')
    const user = userEvent.setup()
    await user.click(toggle)
    expect(screen.getByRole('option', { name: /^Orders Kafka\b/ })).toBeInTheDocument()

    integrationsQuery.mockReturnValue({ data: [option], isPending: false, isFetching: true, isError: false })
    rerender(<IntegrationSelector {...props} />)
    expect(toggle).toBeEnabled()
    expect(toggle).toHaveTextContent('Select a Kafka integration')
    expect(toggle).not.toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('option', { name: /^Orders Kafka\b/ })).toBeInTheDocument()

    integrationsQuery.mockReturnValue({ data: [option], isPending: false, isError: true, refetch: vi.fn() })
    rerender(<IntegrationSelector {...props} value={option.id} />)
    expect(toggle).toHaveTextContent('Orders Kafka')
    expect(screen.getByRole('option', { name: /^Orders Kafka\b/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry loading integrations' })).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('preserves a completed empty Kafka list during a refresh', async () => {
    integrationsQuery.mockReturnValue({ data: [], isPending: false, isFetching: true, isError: false })
    renderSelector({
      integrationType: IntegrationTypeEnum.KAFKA,
      label: 'Integration',
      placeholder: 'Select a Kafka integration',
    })
    const toggle = screen.getByRole('button', { name: 'Integration' })
    expect(toggle).toBeEnabled()
    expect(toggle).not.toHaveAttribute('aria-busy', 'true')
    await userEvent.setup().click(toggle)
    expect(screen.getByRole('option', { name: 'No Kafka integrations available' })).toBeInTheDocument()
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
    expect(integrationsQuery).toHaveBeenCalledWith(IntegrationTypeEnum.MCP_SERVER, 'proj-123')
  })

  it('does not include project_id in the query when projectId is omitted', () => {
    renderSelector()
    expect(integrationsQuery).toHaveBeenCalledWith(IntegrationTypeEnum.MCP_SERVER, undefined)
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
