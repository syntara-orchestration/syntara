import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { accessFetchClient } from './accessClient'
import { MyPermissionsView } from './MyPermissionsView'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const samplePermissions = [
  {
    policy_name: 'admin-policy',
    effect: 'allow',
    actions: ['workflow:read', 'workflow:write'],
    scope: '*',
    project: 'default',
  },
  {
    policy_name: 'deny-delete',
    effect: 'deny',
    actions: ['workflow:delete'],
    scope: 'project',
    project: 'production',
  },
]

function mockPostSuccess(permissions = samplePermissions) {
  vi.mocked(accessFetchClient.POST).mockResolvedValueOnce({
    data: { resources: permissions, next: null, prev: null, total: permissions.length },
    error: undefined,
    response: new Response(),
  })
}

function mockPostError() {
  vi.mocked(accessFetchClient.POST).mockResolvedValueOnce({
    data: undefined,
    error: { detail: 'Internal server error' },
    response: new Response(),
  })
}

function mockPostNetworkError() {
  const err = Object.assign(new Error('Network error'), { status: 500 })
  vi.mocked(accessFetchClient.POST).mockRejectedValueOnce(err)
}

async function renderAndWaitForData(permissions = samplePermissions) {
  mockPostSuccess(permissions)
  const view = render(<MyPermissionsView />, { wrapper })
  await waitFor(() => {
    expect(screen.getByText(permissions[0].policy_name)).toBeInTheDocument()
  })
  return view
}

function generatePermissions(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    policy_name: `policy-${String(i).padStart(3, '0')}`,
    effect: i % 2 === 0 ? 'allow' : 'deny',
    actions: [`action-${i}`],
    scope: `scope-${i}`,
    project: `project-${i}`,
  }))
}

describe('MyPermissionsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(accessFetchClient.POST)
      .mockReset()
      .mockResolvedValue({
        data: { resources: [], next: null, prev: null, total: 0 },
        error: undefined,
        response: new Response(),
      })
  })

  it('auto-loads permissions on mount', async () => {
    await renderAndWaitForData()
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/what_can_i', { body: { limit: 100 } })
  })

  it('shows spinner immediately on mount', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValueOnce(new Promise(() => {}))
    render(<MyPermissionsView />, { wrapper })
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('displays permissions table with data', async () => {
    await renderAndWaitForData()

    expect(screen.getByText('deny-delete')).toBeInTheDocument()
    expect(screen.getByText('allow')).toBeInTheDocument()
    expect(screen.getByText('deny')).toBeInTheDocument()
    expect(screen.getByText('workflow:read')).toBeInTheDocument()
    expect(screen.getByText('workflow:write')).toBeInTheDocument()
    expect(screen.getByText('workflow:delete')).toBeInTheDocument()
  })

  it('renders allow and deny effect labels for mixed permissions', async () => {
    await renderAndWaitForData([
      { policy_name: 'allow-read', effect: 'allow', actions: ['read'], scope: '*', project: 'default' },
      { policy_name: 'deny-delete', effect: 'deny', actions: ['delete'], scope: '*', project: 'default' },
    ])

    expect(screen.getByText('allow-read')).toBeInTheDocument()
    expect(screen.getByText('deny-delete')).toBeInTheDocument()
    expect(screen.getAllByText('allow')).toHaveLength(1)
    expect(screen.getAllByText('deny')).toHaveLength(1)
  })

  it('shows empty state when no permissions exist', async () => {
    mockPostSuccess([])
    render(<MyPermissionsView />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('No permissions')).toBeInTheDocument()
    })
    expect(screen.getByText('The current user has no permissions assigned.')).toBeInTheDocument()
  })

  it('shows error state on API failure', async () => {
    mockPostError()
    render(<MyPermissionsView />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
  })

  it('retries loading when error retry button is clicked', async () => {
    const user = userEvent.setup()
    mockPostNetworkError()
    render(<MyPermissionsView />, { wrapper })

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    mockPostSuccess()
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(screen.getByText('admin-policy')).toBeInTheDocument()
    })
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(2)
  })

  it('shows dash for empty scope and project', async () => {
    await renderAndWaitForData([
      { policy_name: 'test', effect: 'allow', actions: ['workflow:read'], scope: '', project: '' },
    ])

    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('renders refresh button and refreshes on click', async () => {
    const user = userEvent.setup()
    await renderAndWaitForData()

    const refreshBtn = screen.getByRole('button', { name: 'Refresh permissions' })
    expect(refreshBtn).toBeInTheDocument()

    mockPostSuccess([{ policy_name: 'new-policy', effect: 'allow', actions: ['read'], scope: '*', project: 'default' }])

    await user.click(refreshBtn)

    await waitFor(() => {
      expect(screen.getByText('new-policy')).toBeInTheDocument()
    })
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(2)
  })

  it('renders FilterBar with attribute selector', async () => {
    await renderAndWaitForData()
    expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
  })

  it('filters permissions by effect using select filter', async () => {
    const user = userEvent.setup()
    await renderAndWaitForData()

    const toolbar = screen.getByRole('search', { name: 'Filters' })
    await user.click(within(toolbar).getByRole('button', { name: /^Policy$/i }))
    await user.click(await screen.findByRole('option', { name: 'Effect' }))
    await user.click(within(toolbar).getByRole('button', { name: /filter by effect/i }))
    await user.click(await screen.findByRole('option', { name: 'Allow' }))

    await waitFor(() => {
      expect(screen.getByText('admin-policy')).toBeInTheDocument()
      expect(screen.queryByText('deny-delete')).not.toBeInTheDocument()
    })
  })

  it('renders pagination and navigates pages', async () => {
    const perms = generatePermissions(25)
    await renderAndWaitForData(perms)

    const pagination = screen.getByLabelText('Pagination')
    expect(pagination).toBeInTheDocument()

    expect(screen.getByText('policy-000')).toBeInTheDocument()
    expect(screen.queryByText('policy-020')).not.toBeInTheDocument()

    const user = userEvent.setup()
    const nextBtn = within(pagination).getByRole('button', { name: /next/i })
    await user.click(nextBtn)

    await waitFor(() => {
      expect(screen.getByText('policy-020')).toBeInTheDocument()
    })
    expect(screen.queryByText('policy-000')).not.toBeInTheDocument()

    const prevBtn = within(pagination).getByRole('button', { name: /prev/i })
    await user.click(prevBtn)

    await waitFor(() => {
      expect(screen.getByText('policy-000')).toBeInTheDocument()
    })
    expect(screen.queryByText('policy-020')).not.toBeInTheDocument()
  })

  it('shows empty filter state when filters match nothing', async () => {
    const user = userEvent.setup()
    await renderAndWaitForData()

    const toolbar = screen.getByRole('search', { name: 'Filters' })
    await user.type(within(toolbar).getByRole('textbox'), 'nonexistent-policy-xyz')
    await user.click(screen.getByRole('button', { name: 'Apply filter' }))

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })

    const clearButtons = screen.getAllByRole('button', { name: 'Clear all filters' })
    expect(clearButtons.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts by column headers', async () => {
    const user = userEvent.setup()
    await renderAndWaitForData()

    const tableContainer = screen.getByLabelText('User permissions')
    const policyHeader = within(tableContainer).getByRole('button', { name: /policy/i })
    await user.click(policyHeader)

    const rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('admin-policy')).toBeInTheDocument()

    await user.click(policyHeader)

    const rowsAfterSort = screen.getAllByRole('row')
    expect(within(rowsAfterSort[1]).getByText('deny-delete')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    mockPostSuccess([])
    const { container } = render(<MyPermissionsView />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('No permissions')).toBeInTheDocument()
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with permissions loaded', async () => {
    const { container } = await renderAndWaitForData()

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })
})
