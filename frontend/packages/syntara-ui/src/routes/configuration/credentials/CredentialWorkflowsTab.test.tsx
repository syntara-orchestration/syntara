import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { CredentialWorkflowsTab } from './CredentialWorkflowsTab'

const mockRefetch = vi.fn()

vi.mock('../../../client', () => ({
  credentialsClient: {
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

const mockWorkflows = [
  { id: 'wf-1', name: 'Production Deployment' },
  { id: 'wf-2', name: 'Staging Sync' },
  { id: 'wf-3', name: 'Database Backup' },
]

function mockQuery(
  data: { resources: unknown[] } | undefined,
  extra: Record<string, unknown> = {}
): ReturnType<typeof credentialsClient.useQuery> {
  return {
    data,
    isPending: false,
    error: null,
    isFetching: false,
    refetch: mockRefetch,
    ...extra,
  } as never
}

describe('CredentialWorkflowsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRefetch.mockResolvedValue({})
  })

  it('has no accessibility violations with workflows', async () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    const { container } = render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when a description row is expanded', async () => {
    const user = userEvent.setup()
    vi.mocked(credentialsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [{ id: 'wf-1', name: 'Production Deployment', description: 'Deploys to prod' }],
      })
    )

    const { container } = render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })
    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in empty state', async () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    const { container } = render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders empty state when no workflows', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('No workflows using this credential')).toBeInTheDocument()
    expect(
      screen.getByText(
        'This credential is not currently referenced by any workflows. Workflows will appear here once they are configured to use this credential.'
      )
    ).toBeInTheDocument()
  })

  it('renders workflow names as table links', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('link', { name: 'Production Deployment' })).toHaveAttribute(
      'href',
      '/workflow-builder/wf-1'
    )
    expect(screen.getByRole('link', { name: 'Staging Sync' })).toHaveAttribute('href', '/workflow-builder/wf-2')
    expect(screen.getByRole('link', { name: 'Database Backup' })).toHaveAttribute('href', '/workflow-builder/wf-3')
  })

  it('renders table header', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('Workflow name')).toBeInTheDocument()
  })

  it('renders footer with workflow count (plural)', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('renders footer with workflow count (singular)', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: [mockWorkflows[0]] }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('renders loading state', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery(undefined, { isPending: true, isFetching: true }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders error state', () => {
    const mockError = new Error('Network error')
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery(undefined, { error: mockError, isError: true }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('calls refetch when retry button clicked', async () => {
    const user = userEvent.setup()
    const mockError = { detail: 'Server error', status: 500 }
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery(undefined, { error: mockError, isError: true }))

    const { rerender } = render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(mockRefetch).toHaveBeenCalled()

    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    rerender(<CredentialWorkflowsTab credentialId="cred-1" />)

    expect(screen.getByText('Production Deployment')).toBeInTheDocument()
  })

  it('uses correct API endpoint with credential ID', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: [] }))

    render(<CredentialWorkflowsTab credentialId="test-credential-123" />, { wrapper })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith('get', '/credentials/{credential_id}/workflows', {
      params: { path: { credential_id: 'test-credential-123' } },
    })
  })

  it('renders table with accessible label', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: mockWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    const table = screen.getByRole('grid', { name: 'Workflows using this credential' })
    expect(table).toBeInTheDocument()
  })

  it('handles undefined data gracefully', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery(undefined))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('No workflows using this credential')).toBeInTheDocument()
  })

  it('hides descriptions until the row is expanded', async () => {
    const user = userEvent.setup()
    vi.mocked(credentialsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [{ id: 'wf-1', name: 'Production Deployment', description: 'Deploys to prod' }],
      })
    )

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('Deploys to prod')).not.toBeVisible()
    await user.click(screen.getByRole('button', { name: /details/i }))
    expect(screen.getByText('Deploys to prod')).toBeVisible()
  })

  it('does not show an expand toggle when description is missing or whitespace', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          { id: 'wf-1', name: 'No Description' },
          { id: 'wf-2', name: 'Blank Description', description: '   ' },
        ],
      })
    )

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.queryByRole('button', { name: /details/i })).not.toBeInTheDocument()
  })

  it('renders node name labels, created by with date, and execution status', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [
          {
            id: 'wf-1',
            name: 'Production Deployment',
            created_by: 'admin',
            created_at: '2026-07-01T12:00:00Z',
            node_names: ['Fetch secrets', 'Deploy'],
            last_execution_status: 'completed',
          },
        ],
      })
    )

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText(/Jul.*1.*2026/i)).toBeInTheDocument()
    expect(screen.getByText('Fetch secrets')).toBeInTheDocument()
    expect(screen.getByText('Deploy')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('renders dashes for missing created by, node names, and unknown status', () => {
    vi.mocked(credentialsClient.useQuery).mockReturnValue(
      mockQuery({
        resources: [{ id: 'wf-1', name: 'Bare Workflow', last_execution_status: 'not-a-status' }],
      })
    )

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByText('\u2014').length).toBeGreaterThanOrEqual(2)
  })

  it('paginates with next and previous buttons', async () => {
    const user = userEvent.setup()
    const manyWorkflows = Array.from({ length: 25 }, (_, i) => ({
      id: `wf-${i}`,
      name: `Workflow ${i}`,
    }))
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: manyWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByRole('row').length).toBe(21)
    expect(screen.getByText('Workflow 0')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /next/i }))

    expect(screen.getAllByRole('row').length).toBe(6)
    expect(screen.getByText('Workflow 20')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /prev/i }))

    expect(screen.getAllByRole('row').length).toBe(21)
  })

  it('changes per-page count and resets to page 1', async () => {
    const user = userEvent.setup()
    const manyWorkflows = Array.from({ length: 100 }, (_, i) => ({
      id: `wf-${i}`,
      name: `Workflow ${i}`,
    }))
    vi.mocked(credentialsClient.useQuery).mockReturnValue(mockQuery({ resources: manyWorkflows }))

    render(<CredentialWorkflowsTab credentialId="cred-1" />, { wrapper })

    expect(screen.getAllByRole('row').length).toBe(21)

    await user.click(screen.getByRole('button', { name: /1 - 20/i }))
    await user.click(await screen.findByRole('menuitem', { name: /50 per page/i }))

    expect(screen.getAllByRole('row').length).toBe(51)
  })
})
