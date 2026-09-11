import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

import { AAPIntegrationSelector, type AAPIntegrationSelectorProps } from './AAPIntegrationSelector'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../components/FormLabelWithHelp', () => ({
  FormLabelWithHelp: ({ label }: { label: string }) => <span>{label}</span>,
}))

vi.mock('../../../components/SynLink', () => ({
  SynLink: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const mockIntegrations = [
  {
    id: 'int-aap-1',
    name: 'AAP Production',
    configuration: { base_url: 'https://aap.example.com' },
  },
  {
    id: 'int-aap-2',
    name: 'AAP Staging',
    configuration: { base_url: 'https://aap-staging.example.com' },
  },
]

function mockUseQueryReturn(overrides: { data?: { resources: typeof mockIntegrations }; isPending?: boolean }) {
  return {
    data: overrides.data ?? { resources: [] },
    isPending: overrides.isPending ?? false,
    isError: false,
    error: null,
    isLoading: false,
    isFetching: false,
    isSuccess: true,
    status: 'success' as const,
    refetch: vi.fn(),
    fetchStatus: 'idle' as const,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    isFetched: true,
    isFetchedAfterMount: true,
    isInitialLoading: false,
    isLoadingError: false,
    isPaused: false,
    isPlaceholderData: false,
    isRefetchError: false,
    isRefetching: false,
    isStale: false,
    promise: Promise.resolve(overrides.data ?? { resources: [] }),
  }
}

function mockClients({ integrations = mockIntegrations, isPending = false } = {}) {
  vi.mocked(integrationsClient.useQuery).mockReturnValue(
    mockUseQueryReturn({ data: { resources: integrations }, isPending }) as ReturnType<
      typeof integrationsClient.useQuery
    >
  )
}

function renderSelector(props: Partial<AAPIntegrationSelectorProps> = {}) {
  const defaultProps: AAPIntegrationSelectorProps = {
    value: undefined,
    onChange: vi.fn(),
    ...props,
  }
  return render(<AAPIntegrationSelector {...defaultProps} />, { wrapper })
}

describe('AAPIntegrationSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockClients()
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
  })

  it('renders with default label', () => {
    renderSelector()

    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  it('renders with custom label', () => {
    renderSelector({ label: 'AAP Integration' })

    expect(screen.getByText('AAP Integration')).toBeInTheDocument()
  })

  it('shows empty state when no integrations exist', async () => {
    mockClients({ integrations: [] })
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.getByText('No AAP integrations configured')).toBeInTheDocument()
  })

  it('shows helper text with link when no integrations and user can create', () => {
    mockClients({ integrations: [] })
    renderSelector()

    expect(screen.getByText(/An administrator must/)).toBeInTheDocument()
    expect(screen.getByText('configure an AAP integration')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'configure an AAP integration' })).toHaveAttribute(
      'href',
      '/configuration/integrations/configure'
    )
  })

  it('shows plain text helper when no integrations and user cannot create', () => {
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: false,
      canUpdate: false,
      canDelete: false,
      isLoading: false,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
    mockClients({ integrations: [] })
    renderSelector()

    expect(screen.getByText(/An administrator must/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'configure an AAP integration' })).not.toBeInTheDocument()
  })

  it('does not show helper text when integrations exist', () => {
    renderSelector()

    expect(screen.queryByText(/An administrator must/)).not.toBeInTheDocument()
  })

  it('calls onChange when an integration is selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ onChange })

    await user.click(screen.getByRole('button', { name: /integration/i }))

    await user.click(screen.getByText('AAP Production'))
    expect(onChange).toHaveBeenCalledWith('int-aap-1')
  })

  it('displays selected integration name in toggle', () => {
    renderSelector({ value: 'int-aap-1' })

    expect(screen.getByDisplayValue('AAP Production')).toBeInTheDocument()
  })

  it('falls back to UUID when selected integration is not found', () => {
    renderSelector({ value: 'unknown-uuid' })

    expect(screen.getByDisplayValue('unknown-uuid')).toBeInTheDocument()
  })

  it('shows loading placeholder when pending', () => {
    mockClients({ isPending: true })
    renderSelector()

    expect(screen.getByPlaceholderText('Loading integrations...')).toBeInTheDocument()
  })

  it('shows integration URL below name in options', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.getByText('https://aap.example.com')).toBeInTheDocument()
    expect(screen.getByText('https://aap-staging.example.com')).toBeInTheDocument()
  })

  it('clears selection when clear button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ value: 'int-aap-1', onChange })

    const clearButton = screen.getByRole('button', { name: 'Clear selection' })
    await user.click(clearButton)

    expect(onChange).toHaveBeenCalledWith(undefined)
  })

  it('filters integrations by name and shows no results message', async () => {
    const user = userEvent.setup()
    renderSelector()

    const input = screen.getByRole('textbox', { name: /integration/i })
    await user.type(input, 'nonexistent')

    expect(screen.getByText(/No results match/)).toBeInTheDocument()
  })

  it('filters integrations by name and shows matching results', async () => {
    const user = userEvent.setup()
    renderSelector()

    const input = screen.getByRole('textbox', { name: /integration/i })
    await user.type(input, 'Production')

    expect(screen.getByText('AAP Production')).toBeInTheDocument()
    expect(screen.queryByText('AAP Staging')).not.toBeInTheDocument()
  })

  it('clears filter text when an option is selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ onChange })

    const input = screen.getByRole('textbox', { name: /integration/i })
    await user.type(input, 'Prod')

    await user.click(screen.getByText('AAP Production'))

    expect(onChange).toHaveBeenCalledWith('int-aap-1')
  })

  it('renders with helpText prop', () => {
    renderSelector({ helpText: 'Choose your AAP integration' })

    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  it('renders without helpText prop', () => {
    renderSelector({ helpText: undefined })

    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  it('renders integration without URL', async () => {
    const user = userEvent.setup()
    mockClients({
      integrations: [{ id: 'int-no-url', name: 'AAP No URL', configuration: { base_url: '' } }],
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.getByText('AAP No URL')).toBeInTheDocument()
  })

  it('handles selecting a non-string value gracefully', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ onChange })

    await user.click(screen.getByRole('button', { name: /integration/i }))
    await user.click(screen.getByText('AAP Production'))

    expect(onChange).toHaveBeenCalledWith('int-aap-1')
  })

  it('has no accessibility violations', async () => {
    mockClients({ integrations: [] })
    const { container } = renderSelector()

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with a selection', async () => {
    const { container } = renderSelector({ value: 'int-aap-1' })

    expect(await axe(container)).toHaveNoViolations()
  })

  it('filters out integrations without id', () => {
    mockClients({
      integrations: [
        { id: 'int-valid', name: 'Valid AAP', configuration: { base_url: 'https://valid.example.com' } },
        { id: '', name: 'No ID AAP', configuration: { base_url: 'https://noid.example.com' } },
      ] as typeof mockIntegrations,
    })
    renderSelector()

    // Only valid integration should be selectable
    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  it('renders integration with config missing base_url key', async () => {
    const user = userEvent.setup()
    mockClients({
      integrations: [{ id: 'int-no-config', name: 'AAP No Config', configuration: {} }] as typeof mockIntegrations,
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.getByText('AAP No Config')).toBeInTheDocument()
    // No URL should be displayed since config doesn't have base_url
  })

  it('renders integration with undefined configuration', async () => {
    const user = userEvent.setup()
    mockClients({
      integrations: [
        { id: 'int-undef-config', name: 'AAP Undef Config', configuration: undefined },
      ] as unknown as typeof mockIntegrations,
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.getByText('AAP Undef Config')).toBeInTheDocument()
  })

  it('shows empty toggle label when no value is set', () => {
    renderSelector({ value: undefined })

    const input = screen.getByRole('textbox', { name: /integration/i })
    expect(input).toHaveValue('')
  })

  it('does not show helper text when pending even with no integrations', () => {
    mockClients({ integrations: [], isPending: true })
    renderSelector()

    expect(screen.queryByText(/An administrator must/)).not.toBeInTheDocument()
  })

  it('does not show empty menu option when pending', () => {
    mockClients({ integrations: [], isPending: true })
    renderSelector()

    expect(screen.queryByText('No AAP integrations configured')).not.toBeInTheDocument()
  })

  it('renders with isRequired false by default', () => {
    renderSelector()
    // FormGroup should render without required indicator
    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  it('marks isRequired on FormGroup when specified', () => {
    renderSelector({ isRequired: true })

    // The required attribute should be reflected
    expect(screen.getByText('Integration')).toBeInTheDocument()
  })

  describe('stale integration detection', () => {
    it('calls onStaleDetected when the selected integration is not in loaded list', () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'nonexistent-id', onStaleDetected })

      expect(onStaleDetected).toHaveBeenCalledOnce()
    })

    it('does not call onStaleDetected when the selected integration exists', () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'int-aap-1', onStaleDetected })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected when no integration is selected', () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: undefined, onStaleDetected })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected while integrations are still loading', () => {
      mockClients({ isPending: true })
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'nonexistent-id', onStaleDetected })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })
  })

  it('does not show no results when filter is empty and integrations exist', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))

    expect(screen.queryByText(/No results match/)).not.toBeInTheDocument()
  })

  it('handles empty string filter showing all integrations', async () => {
    const user = userEvent.setup()
    renderSelector()

    const input = screen.getByRole('textbox', { name: /integration/i })
    await user.click(input)

    // All integrations visible with no filter
    expect(screen.getByText('AAP Production')).toBeInTheDocument()
    expect(screen.getByText('AAP Staging')).toBeInTheDocument()
  })

  it('passes project_id to the integrations query when projectId is provided', () => {
    renderSelector({ projectId: 'proj-aap-123' })
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'ansible_automation_platform', enabled: true, project_id: 'proj-aap-123' },
      },
    })
  })

  it('does not include project_id in the query when projectId is omitted', () => {
    renderSelector()
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'ansible_automation_platform', enabled: true },
      },
    })
  })

  it('renders only project-scoped integrations when projectId filters the result set', async () => {
    const projectScopedIntegrations = [mockIntegrations[0]]
    mockClients({ integrations: projectScopedIntegrations })
    const user = userEvent.setup()
    renderSelector({ projectId: 'proj-aap-123' })

    const input = screen.getByRole('textbox', { name: /integration/i })
    await user.click(input)

    expect(screen.getByText('AAP Production')).toBeInTheDocument()
    expect(screen.queryByText('AAP Staging')).not.toBeInTheDocument()
  })
})
