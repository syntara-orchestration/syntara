import { IntegrationStatusEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { CredentialIntegrationsTab } from './CredentialIntegrationsTab'

const mockRefetch = vi.fn()

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockIntegrations = [
  {
    id: 'int-1',
    name: 'GitHub Copilot',
    integration_type: 'mcp_server',
    validation_status: 'available',
    scope: 'global',
  },
  {
    id: 'int-2',
    name: 'Jira Integration',
    integration_type: 'mcp_server',
    validation_status: IntegrationStatusEnum.ERROR,
    validation_error: 'Connection refused',
    scope: 'global',
  },
  {
    id: 'int-3',
    name: 'Red Hat AI',
    integration_type: 'llm_provider',
    validation_status: 'available',
    scope: 'project',
  },
]

function mockQuery(
  data: { resources: unknown[] } | undefined,
  extra: Record<string, unknown> = {}
): ReturnType<typeof integrationsClient.useQuery> {
  return {
    data,
    isPending: false,
    error: null,
    isFetching: false,
    refetch: mockRefetch,
    ...extra,
  } as never
}

describe('CredentialIntegrationsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRefetch.mockResolvedValue({})
  })

  it('has no accessibility violations with integrations', async () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    const { container } = render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when a description row is expanded', async () => {
    const user = userEvent.setup()
    vi.mocked(integrationsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: 'int-1',
            name: 'GitHub Copilot',
            description: 'AI coding assistant',
            integration_type: 'mcp_server',
            validation_status: 'available',
            scope: 'global',
          },
        ],
      })
    )

    const { container } = render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })
    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in empty state', async () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    const { container } = render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders empty state when no integrations', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('No integrations yet')).toBeInTheDocument()
    expect(
      screen.getByText(
        'This credential is not currently referenced by any integrations. Integrations will appear here once they are configured to use this credential.'
      )
    ).toBeInTheDocument()
  })

  it('renders integration names as table links', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('link', { name: 'GitHub Copilot' })).toHaveAttribute(
      'href',
      '/configuration/integrations/int-1'
    )
    expect(screen.getByRole('link', { name: 'Jira Integration' })).toHaveAttribute(
      'href',
      '/configuration/integrations/int-2'
    )
    expect(screen.getByRole('link', { name: 'Red Hat AI' })).toHaveAttribute(
      'href',
      '/configuration/integrations/int-3'
    )
  })

  it('renders table headers', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('Integration name')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Scope')).toBeInTheDocument()
  })

  it('renders footer with pagination', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('renders footer with singular count', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: [mockIntegrations[0]] }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('renders loading state', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery(undefined, { isPending: true, isFetching: true }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders error state', () => {
    const mockError = new Error('Network error')
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery(undefined, { error: mockError, isError: true }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('calls refetch when retry button clicked', async () => {
    const user = userEvent.setup()
    const mockError = { detail: 'Server error', status: 500 }
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery(undefined, { error: mockError, isError: true }))

    const { rerender } = render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(mockRefetch).toHaveBeenCalled()

    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    rerender(<CredentialIntegrationsTab credentialId="cred-1" />)

    expect(screen.getByText('GitHub Copilot')).toBeInTheDocument()
  })

  it('uses correct API endpoint with credential ID', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    render(<CredentialIntegrationsTab credentialId="test-credential-123" />, { wrapper })

    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: { query: { management_credential_id: 'test-credential-123' } },
    })
  })

  it('renders table with accessible label', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    const table = screen.getByRole('grid', { name: 'Integrations using this credential' })
    expect(table).toBeInTheDocument()
  })

  it('handles undefined data gracefully', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery(undefined))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('No integrations yet')).toBeInTheDocument()
  })

  it('displays integration type labels correctly', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByText('MCP Server').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('LLM Provider')).toBeInTheDocument()
  })

  it('shows validation error tooltip on hover for error status', async () => {
    const user = userEvent.setup()
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    const errorLabels = screen.getAllByText('Error')
    await user.hover(errorLabels[0])
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Connection refused')
  })

  it('displays scope correctly', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: mockIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByText('Global').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Project')).toBeInTheDocument()
  })

  it('hides descriptions until the row is expanded', async () => {
    const user = userEvent.setup()
    vi.mocked(integrationsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: 'int-1',
            name: 'GitHub Copilot',
            description: 'AI coding assistant',
            integration_type: 'mcp_server',
            validation_status: 'available',
            scope: 'global',
            created_by: 'admin',
          },
        ],
      })
    )

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('AI coding assistant')).not.toBeVisible()
    await user.click(screen.getByRole('button', { name: /details/i }))
    expect(screen.getByText('AI coding assistant')).toBeVisible()
  })

  it('renders Created by column with username and date', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: 'int-1',
            name: 'GitHub Copilot',
            integration_type: 'mcp_server',
            validation_status: 'available',
            scope: 'global',
            created_by: 'admin',
            created_at: '2026-07-01T12:00:00Z',
          },
        ],
      })
    )

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('Created by')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText(/Jul.*1.*2026/i)).toBeInTheDocument()
  })

  it('links to an empty integration id when the id is missing', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: null,
            name: 'No ID Integration',
            integration_type: 'mcp_server',
            validation_status: 'available',
            scope: 'global',
            created_by: 'admin',
          },
        ],
      })
    )

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('link', { name: 'No ID Integration' })).toHaveAttribute(
      'href',
      '/configuration/integrations/'
    )
  })

  it('paginates with next and previous buttons', async () => {
    const user = userEvent.setup()
    const manyIntegrations = Array.from({ length: 25 }, (_, i) => ({
      id: `int-${i}`,
      name: `Integration ${i}`,
      integration_type: 'mcp_server',
      validation_status: 'available',
      scope: 'global',
      created_by: 'admin',
    }))
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: manyIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByRole('row').length).toBe(21)
    expect(screen.getByText('Integration 0')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.getAllByRole('row').length).toBe(6)
    expect(screen.getByText('Integration 20')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /prev/i }))

    expect(screen.getAllByRole('row').length).toBe(21)
  })

  it('renders integration with missing optional fields', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: null,
            name: 'Bare Integration',
            integration_type: null,
            validation_status: null,
            scope: 'project',
            created_by: null,
          },
        ],
      })
    )

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('Bare Integration')).toBeInTheDocument()
    expect(screen.getByText('Project')).toBeInTheDocument()
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('changes per-page count and resets to page 1', async () => {
    const user = userEvent.setup()
    const manyIntegrations = Array.from({ length: 100 }, (_, i) => ({
      id: `int-${i}`,
      name: `Integration ${i}`,
      integration_type: 'mcp_server',
      validation_status: 'available',
      scope: 'global',
      created_by: 'admin',
    }))
    vi.mocked(integrationsClient.useQuery).mockReturnValue(mockQuery({ resources: manyIntegrations }))

    render(<CredentialIntegrationsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByRole('row').length).toBe(21)

    const perPageToggle = screen.getByRole('button', { name: /1 - 20/i })
    await user.click(perPageToggle)

    const option50 = await screen.findByRole('menuitem', { name: /50 per page/i })
    await user.click(option50)

    expect(screen.getAllByRole('row').length).toBe(51)
  })
})
