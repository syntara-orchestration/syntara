import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { executionPlaneClient } from '../../client'
import { useCanI } from '../../hooks/useCanI'
import { AlertProvider } from '../../providers/alerts'
import { assertUrlParam } from '../../test/filter-test-helpers'
import { expectPageTitle } from '../../test/pageTitle'
import { routerTestState } from '../../test/setup'

import ExecutionPlane from './ExecutionPlane'

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('wouter', () => ({
  useLocation: () => ['/execution-plane', routerTestState.navigate],
}))

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/execution-plane',
}))

const mockSearchParams = new URLSearchParams()
const mockSetSearchParams = vi.fn()

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}))

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

const mockTargets = [
  {
    id: 'et-001',
    cluster_id: 'cl-001',
    name: 'Prod OpenShift West',
    backend_type: 'kubernetes',
    endpoint: 'https://api.west.example.com',
    placement: { type: 'kubernetes' as const, namespace: 'syntara-workers', node_selectors: [], tolerations: [] },
    status: 'ready',
    enabled: true,
    is_default: true,
    status_message: null,
    labels: { region: 'us-west', env: 'prod' },
    created_at: '2026-01-01T00:00:00Z',
    last_ran_at: null,
  },
  {
    id: 'et-002',
    cluster_id: 'cl-002',
    name: 'Staging OpenShift',
    backend_type: 'kubernetes',
    endpoint: 'https://api.staging.example.com',
    placement: { type: 'kubernetes' as const, namespace: 'syntara-staging', node_selectors: [], tolerations: [] },
    status: 'provisioning',
    enabled: false,
    is_default: false,
    status_message: 'Waiting for workers',
    labels: { env: 'staging' },
    created_at: '2026-01-02T00:00:00Z',
    last_ran_at: null,
  },
]

function mockFacadeQuery(overrides: Record<string, unknown> = {}) {
  vi.mocked(executionPlaneClient.useQuery).mockReturnValue({
    data: { resources: mockTargets, next: null, prev: null, total: mockTargets.length },
    isPending: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as ReturnType<typeof executionPlaneClient.useQuery>)
}

describe('ExecutionPlane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSearchParams.forEach((_value, key) => mockSearchParams.delete(key))
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
    mockFacadeQuery()
  })

  it('lists execution targets with required columns', async () => {
    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Execution Plane' })).toBeInTheDocument()
    expectPageTitle(['Execution Plane'])
    expect(screen.getByText('Prod OpenShift West')).toBeInTheDocument()
    expect(screen.getByText('Staging OpenShift')).toBeInTheDocument()
    expect(screen.getByText('cl-001')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('region=us-west')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Prod OpenShift West.*Enabled/ })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Staging OpenShift.*Disabled/ })).toBeInTheDocument()
  })

  it('requests execution targets from the facade endpoint with cursor query params', () => {
    render(<ExecutionPlane />, { wrapper })

    const call = vi.mocked(executionPlaneClient.useQuery).mock.calls[0]
    expect(call?.[0]).toBe('get')
    expect(call?.[1]).toBe('/api/execution_plane/v1/execution_targets')
    const queryParams = (call?.[2] as { params?: { query?: Record<string, unknown> } } | undefined)?.params?.query
    expect(queryParams).toMatchObject({
      limit: 20,
      include_total: true,
      sort: 'name',
    })
  })

  it('configures 30-second polling interval on the execution targets query', () => {
    render(<ExecutionPlane />, { wrapper })

    const call = vi.mocked(executionPlaneClient.useQuery).mock.calls[0]
    const queryOptions = call?.[3] as { refetchInterval?: number } | undefined
    expect(queryOptions?.refetchInterval).toBe(30_000)
  })

  it('wires pagination footer from facade response cursors and total', async () => {
    mockFacadeQuery({
      data: {
        resources: mockTargets,
        next: 'next-cursor',
        prev: null,
        total: 42,
      },
    })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByText('Prod OpenShift West')).toBeInTheDocument()
    expect(screen.queryAllByText((_, el) => (el?.textContent ?? '').includes('of 42'))).not.toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Go to next page' })).toBeEnabled()
  })

  it('shows empty state with configure path when no targets exist', async () => {
    mockFacadeQuery({ data: { resources: [], next: null, prev: null, total: 0 } })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByText('No execution targets yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Configure integration' })).toBeInTheDocument()
  })

  it('hides configure action in empty state when user cannot create integrations', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    mockFacadeQuery({ data: { resources: [], next: null, prev: null, total: 0 } })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByText('No execution targets yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Configure integration' })).not.toBeInTheDocument()
  })

  it('shows filter-empty state and toolbar when filters are active but no targets match', async () => {
    mockSearchParams.set('name[contains]', 'no-match')
    mockFacadeQuery({ data: { resources: [], next: null, prev: null, total: 0 } })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByText('No results found')).toBeInTheDocument()
    expect(screen.queryByText('No execution targets yet')).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('Filter by name')).toBeInTheDocument()
  })

  it('shows loading state while the facade query is pending', () => {
    mockFacadeQuery({
      data: undefined,
      isPending: true,
      isFetching: true,
      error: null,
    })

    render(<ExecutionPlane />, { wrapper })

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('shows error state when the facade query fails', async () => {
    mockFacadeQuery({
      data: undefined,
      error: { title: 'Internal Error', detail: 'boom', status: 500 },
      isPending: false,
    })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByRole('heading', { name: 'Error loading execution targets' })).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
    expect(screen.queryByText('Prod OpenShift West')).not.toBeInTheDocument()
  })

  it('retries the facade query when Retry is clicked', async () => {
    const user = userEvent.setup()
    const refetch = vi.fn().mockResolvedValue(undefined)
    mockFacadeQuery({
      data: undefined,
      error: { title: 'Internal Error', detail: 'boom', status: 500, retryable: true },
      isPending: false,
      refetch,
    })

    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByRole('heading', { name: 'Error loading execution targets' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('writes name filter to URL search params', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlane />, { wrapper })

    expect(await screen.findByText('Prod OpenShift West')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Filter by name'), 'staging')
    await user.keyboard('{Enter}')

    assertUrlParam(mockSetSearchParams, 'name[contains]', 'staging')
  })

  it('renders sortable headers for name, cluster, status, and state', () => {
    render(<ExecutionPlane />, { wrapper })

    for (const name of [/^Name$/i, /^Cluster$/i, /^Status$/i, /^State$/i]) {
      const header = screen.getByRole('columnheader', { name })
      expect(within(header).getByRole('button')).toBeInTheDocument()
    }

    const labelsHeader = screen.getByRole('columnheader', { name: /Routing labels/i })
    expect(within(labelsHeader).queryByRole('button')).not.toBeInTheDocument()
  })

  it('writes sort URL param when a column header is clicked', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlane />, { wrapper })

    const statusHeader = screen.getByRole('columnheader', { name: /^Status$/i })
    await user.click(within(statusHeader).getByRole('button'))

    await waitFor(() => {
      assertUrlParam(mockSetSearchParams, 'sort', 'status')
    })
  })

  it('can sort by cluster_id via the Cluster column', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlane />, { wrapper })

    const clusterHeader = screen.getByRole('columnheader', { name: /^Cluster$/i })
    await user.click(within(clusterHeader).getByRole('button'))

    await waitFor(() => {
      assertUrlParam(mockSetSearchParams, 'sort', 'cluster_id')
    })
  })

  it('can sort by enabled via the State column', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlane />, { wrapper })

    const stateHeader = screen.getByRole('columnheader', { name: /^State$/i })
    await user.click(within(stateHeader).getByRole('button'))

    await waitFor(() => {
      assertUrlParam(mockSetSearchParams, 'sort', 'enabled')
    })
  })

  it('toggles sort direction when clicking the default name column', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlane />, { wrapper })

    const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
    await user.click(within(nameHeader).getByRole('button'))

    await waitFor(() => {
      assertUrlParam(mockSetSearchParams, 'sort', '-name')
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionPlane />, { wrapper })
    await screen.findByRole('heading', { level: 1, name: 'Execution Plane' })
    expect(await axe(container)).toHaveNoViolations()
  })
})
