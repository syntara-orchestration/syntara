import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { executionPlaneClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { expectPageTitle } from '../../test/pageTitle'

import ExecutionTargetDetail from './ExecutionTargetDetail'

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
      <a href={String(to)} {...rest}>
        {children}
      </a>
    ),
    useNavigate: () => mockNavigate,
    useParams: vi.fn(() => ({ executionTargetId: 'et-001' })),
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: '/execution-plane/et-001', searchStr: '' } }
      return opts?.select ? opts.select(state) : state
    },
  }
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockTarget = {
  id: 'et-001',
  cluster_id: 'cl-001',
  name: 'Prod OpenShift West',
  backend_type: 'kubernetes',
  endpoint: 'https://api.west.example.com',
  placement: {
    type: 'kubernetes' as const,
    namespace: 'syntara-workers',
    node_selectors: ['workload=automation'],
    tolerations: [],
  },
  status: 'active',
  enabled: true,
  is_default: true,
  status_message: null,
  labels: { region: 'us-west', env: 'prod', integration_id: 'integration-001' },
  created_at: '2026-01-01T00:00:00Z',
  last_ran_at: null,
}

function mockFacadeQuery(overrides: Record<string, unknown> = {}) {
  vi.mocked(executionPlaneClient.useQuery).mockReturnValue({
    data: mockTarget,
    isPending: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as ReturnType<typeof executionPlaneClient.useQuery>)
}

describe('ExecutionTargetDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useParams).mockReturnValue({ executionTargetId: 'et-001' })
    mockFacadeQuery()
  })

  it('requests the target by id from the facade', () => {
    render(<ExecutionTargetDetail />, { wrapper })

    const call = vi.mocked(executionPlaneClient.useQuery).mock.calls[0]
    expect(call?.[0]).toBe('get')
    expect(call?.[1]).toBe('/api/execution_plane/v1/execution_targets/{target_id}')
    expect(call?.[2]).toEqual({
      params: { path: { target_id: 'et-001' } },
    })
  })

  it('renders stored facade fields for a matching target', async () => {
    render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Prod OpenShift West' })).toBeInTheDocument()
    expectPageTitle(['Prod OpenShift West', 'Execution Plane'])
    expect(screen.getByRole('heading', { level: 2, name: 'General' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Routing' })).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('OpenShift Cluster')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'cl-001' })).toHaveAttribute(
      'href',
      '/configuration/integrations/integration-001'
    )
    expect(screen.getByText('Execution namespace')).toBeInTheDocument()
    expect(screen.getByText('syntara-workers')).toBeInTheDocument()
    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('workload=automation')).toBeInTheDocument()
    expect(screen.queryByText('region=us-west')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('shows Cluster as plain text when integration_id label is absent', async () => {
    mockFacadeQuery({
      data: { ...mockTarget, labels: { region: 'us-west' } },
    })

    render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByText('cl-001')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'cl-001' })).not.toBeInTheDocument()
  })

  it('shows em dash for execution namespace on RHEL placement', async () => {
    mockFacadeQuery({
      data: {
        ...mockTarget,
        name: 'RHEL Edge Lab',
        placement: { type: 'rhel' as const },
        enabled: false,
        labels: {},
      },
    })

    render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'RHEL Edge Lab' })).toBeInTheDocument()
    expect(screen.getByText('Disabled')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
  })

  it('shows not-found state with back and retry on 404', async () => {
    const user = userEvent.setup()
    const refetch = vi.fn()
    mockFacadeQuery({
      data: undefined,
      error: Object.assign(new Error('Not found'), { status: 404 }),
      refetch,
    })

    render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByRole('heading', { name: 'Execution target not found' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Back to Execution Plane' }))
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/execution-plane' })
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('shows SynErrorState when no execution target id is provided', () => {
    vi.mocked(useParams).mockReturnValue({ executionTargetId: '' })

    render(<ExecutionTargetDetail />, { wrapper })

    expect(screen.getByText('Invalid execution target')).toBeInTheDocument()
    expect(screen.getByText('No execution target ID provided')).toBeInTheDocument()
  })

  it('shows SynErrorState when the facade query fails', async () => {
    mockFacadeQuery({
      data: undefined,
      error: { status: 500, message: 'boom' },
      isPending: false,
    })

    render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Error loading execution target' })).toBeInTheDocument()
  })

  it('has no accessibility violations on the details view', async () => {
    const { container } = render(<ExecutionTargetDetail />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Prod OpenShift West' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
