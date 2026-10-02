import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

import { TFEIntegrationSelector, type TFEIntegrationSelectorProps } from './TFEIntegrationSelector'

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
    id: 'int-tfe-1',
    name: 'TFE Production',
    configuration: { base_url: 'https://app.terraform.io', organization: 'acme' },
  },
  {
    id: 'int-tfe-2',
    name: 'TFE Staging',
    configuration: { base_url: 'https://tfe.example.com', organization: 'staging' },
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

function renderSelector(props: Partial<TFEIntegrationSelectorProps> = {}) {
  const defaultProps: TFEIntegrationSelectorProps = {
    value: undefined,
    onChange: vi.fn(),
    ...props,
  }
  return render(<TFEIntegrationSelector {...defaultProps} />, { wrapper })
}

describe('TFEIntegrationSelector', () => {
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
    renderSelector({ label: 'TFE Integration' })
    expect(screen.getByText('TFE Integration')).toBeInTheDocument()
  })

  it('shows empty state when no integrations exist', async () => {
    mockClients({ integrations: [] })
    const user = userEvent.setup()
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))
    expect(screen.getByText('No TFE integrations configured')).toBeInTheDocument()
  })

  it('shows helper text with link when no integrations and user can create', () => {
    mockClients({ integrations: [] })
    renderSelector()

    expect(screen.getByText(/An administrator must/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /configure a Terraform Enterprise integration/i })).toHaveAttribute(
      'href',
      '/configuration/integrations/configure'
    )
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
    await user.click(screen.getByText('TFE Production'))
    expect(onChange).toHaveBeenCalledWith('int-tfe-1')
  })

  it('displays selected integration name in toggle', () => {
    renderSelector({ value: 'int-tfe-1' })
    expect(screen.getByDisplayValue('TFE Production')).toBeInTheDocument()
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
    expect(screen.getByText('https://app.terraform.io')).toBeInTheDocument()
    expect(screen.getByText('https://tfe.example.com')).toBeInTheDocument()
  })

  it('clears selection when clear button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ value: 'int-tfe-1', onChange })

    await user.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(onChange).toHaveBeenCalledWith(undefined)
  })

  it('filters integrations by name and shows no results message', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.type(screen.getByRole('textbox', { name: /integration/i }), 'nonexistent')
    expect(screen.getByText(/No results match/)).toBeInTheDocument()
  })

  it('filters integrations by name and shows matching results', async () => {
    const user = userEvent.setup()
    renderSelector()

    await user.type(screen.getByRole('textbox', { name: /integration/i }), 'Production')
    expect(screen.getByText('TFE Production')).toBeInTheDocument()
    expect(screen.queryByText('TFE Staging')).not.toBeInTheDocument()
  })

  it('renders integration without URL', async () => {
    const user = userEvent.setup()
    mockClients({
      integrations: [{ id: 'int-no-url', name: 'TFE No URL', configuration: { base_url: '', organization: 'org' } }],
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))
    expect(screen.getByText('TFE No URL')).toBeInTheDocument()
  })

  it('renders integration with undefined configuration', async () => {
    const user = userEvent.setup()
    mockClients({
      integrations: [
        { id: 'int-undef', name: 'TFE Undef', configuration: undefined },
      ] as unknown as typeof mockIntegrations,
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /integration/i }))
    expect(screen.getByText('TFE Undef')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    mockClients({ integrations: [] })
    const { container } = renderSelector()
    expect(await axe(container)).toHaveNoViolations()
  })

  describe('stale integration detection', () => {
    it('calls onStaleDetected when the selected integration is not in loaded list', () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'nonexistent-id', onStaleDetected })
      expect(onStaleDetected).toHaveBeenCalledOnce()
    })

    it('does not call onStaleDetected when the selected integration exists', () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'int-tfe-1', onStaleDetected })
      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected while integrations are still loading', () => {
      mockClients({ isPending: true })
      const onStaleDetected = vi.fn()
      renderSelector({ value: 'nonexistent-id', onStaleDetected })
      expect(onStaleDetected).not.toHaveBeenCalled()
    })
  })

  it('passes project_id to the integrations query when projectId is provided', () => {
    renderSelector({ projectId: 'proj-tfe-123' })
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'terraform_enterprise', enabled: true, project_id: 'proj-tfe-123' },
      },
    })
  })

  it('does not include project_id in the query when projectId is omitted', () => {
    renderSelector()
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'terraform_enterprise', enabled: true },
      },
    })
  })
})
