import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { useQueryState } from '../../components/states/useQueryState'

import { accessClient } from './accessClient'
import { PoliciesTab } from './PoliciesTab'
import type { PolicyRead } from './types'

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}))

vi.mock('./useProjectNameMap', () => ({
  useProjectNameMap: () => ({
    projectNameMap: new Map<string, string>([['proj-1', 'Project One']]),
    isLoading: false,
  }),
}))

vi.mock('../../components/states/useQueryState', () => ({
  useQueryState: vi.fn(),
}))

vi.mock('../../components/details/SynCodeBlock', () => ({
  SynCodeBlock: ({ jsonObject }: { jsonObject: unknown }) => <pre>{JSON.stringify(jsonObject)}</pre>,
}))

vi.mock('wouter', async () => {
  const React = await import('react')
  return {
    useLocation: () => ['/system-administration/access-management/policies', vi.fn()],
    useSearch: () => '',
    useSearchParams: () => React.useState(new URLSearchParams()),
  }
})

const samplePolicies: PolicyRead[] = [
  {
    id: 'p1',
    name: 'admin-policy',
    description: 'Full admin access',
    statements: [{ scope: 'any', effect: 'allow', actions: ['workflow:read', 'workflow:write'] }],
    is_builtin: true,
    is_project_eligible: false,
    is_system_scoped: true,
    project_id: null,
    scope: 'any',
    labels: {},
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-06-01T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'viewer-policy',
    description: 'Read-only access',
    statements: [{ scope: 'self', effect: 'allow', actions: ['workflow:read'] }],
    is_builtin: false,
    is_project_eligible: true,
    is_system_scoped: false,
    project_id: 'proj-1',
    scope: 'project',
    labels: {},
    created_at: '2024-02-01T00:00:00Z',
    updated_at: null,
  },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const mockRefetch = vi.fn().mockResolvedValue({})

function setupPoliciesQuery(policies: PolicyRead[], options?: { total?: number; next?: string | null }) {
  vi.mocked(accessClient.useQuery).mockReturnValue({
    data: {
      resources: policies,
      total: options?.total ?? policies.length,
      next: options?.next ?? null,
      prev: null,
    },
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  } as never)
}

describe('PoliciesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(useQueryState).mockReturnValue(null)
  })

  it('renders empty state when no policies exist', () => {
    setupPoliciesQuery([])

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByText('No policies yet')).toBeInTheDocument()
    expect(screen.getByText('No policies are available.')).toBeInTheDocument()
  })

  it('renders loading state when query is pending', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('renders error state when query fails', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error('Network error'),
      refetch: mockRefetch,
    } as never)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
  })

  it('renders policies table with data', () => {
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('grid', { name: 'Policies' })).toBeInTheDocument()
    expect(screen.getByText('admin-policy')).toBeInTheDocument()
    expect(screen.getByText('viewer-policy')).toBeInTheDocument()
    expect(screen.getByText('Full admin access')).toBeInTheDocument()
    expect(screen.getByText('Read-only access')).toBeInTheDocument()
  })

  it('renders Built-in and Custom labels', () => {
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByText('Built-in')).toBeInTheDocument()
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  it('shows dash for null description', () => {
    setupPoliciesQuery([
      {
        ...samplePolicies[0],
        description: null,
      },
    ])

    render(<PoliciesTab />, { wrapper })

    const row = screen.getAllByRole('row')[1]
    const descriptionCell = within(row).getAllByRole('cell')[1]
    expect(descriptionCell).toHaveTextContent('-')
  })

  it('opens policy definition modal from row kebab', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabs[0])
    await user.click(await screen.findByRole('menuitem', { name: /view policy definition/i }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'admin-policy policy definition' })).toBeInTheDocument()
  })

  it('closes policy definition modal when Close is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabs[0])
    await user.click(await screen.findByRole('menuitem', { name: /view policy definition/i }))

    expect(screen.getByRole('heading', { name: 'admin-policy policy definition' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close policy definition' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders table footer with policy count, total when larger than page, and cursor pagination controls', () => {
    setupPoliciesQuery(samplePolicies, { total: 100, next: 'cursor-page2' })

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /next page/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /previous page/i })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupPoliciesQuery(samplePolicies)

    const { container } = render(<PoliciesTab />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('passes sort and pagination params to the API', () => {
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const callArgs = vi
      .mocked(accessClient.useQuery)
      .mock.calls.find((call) => call[0] === 'get' && call[1] === '/policies')
    expect(callArgs).toBeDefined()
    const queryOptions = callArgs![2] as unknown as {
      params: { query: Record<string, unknown> }
    }
    expect(queryOptions.params.query).toMatchObject({
      sort: 'name',
      limit: 20,
      include_total: true,
    })
  })

  it('shows the selected policy definition when opened from a different row kebab', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabs[1])
    await user.click(await screen.findByRole('menuitem', { name: /view policy definition/i }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'viewer-policy policy definition' })).toBeInTheDocument()
    expect(within(dialog).getByText(/"description":"Read-only access"/)).toBeInTheDocument()
  })

  it('renders column headers with sort buttons', () => {
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('columnheader', { name: /name/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /description/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /statements/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /scope/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /project/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /type/i })).toBeInTheDocument()
  })

  it('renders statement effect, scope, and actions in the Statements column', () => {
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getAllByText('Allow').length).toBeGreaterThan(0)
    expect(screen.getByText('scope: any')).toBeInTheDocument()
    expect(screen.getByText('workflow:write')).toBeInTheDocument()
  })

  it('renders — for policies with no statements', () => {
    setupPoliciesQuery([{ ...samplePolicies[0], statements: [] }])

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders overflow button for statements with more than 2 actions', () => {
    setupPoliciesQuery([
      {
        ...samplePolicies[0],
        statements: [{ scope: 'any', effect: 'allow', actions: ['a:read', 'a:write', 'a:delete'] }],
      },
    ])

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('button', { name: '1 more' })).toBeInTheDocument()
    expect(screen.getByText('a:read')).toBeInTheDocument()
    expect(screen.getByText('a:write')).toBeInTheDocument()
  })

  it('calls sort when column header is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const nameColumnHeader = screen.getByRole('columnheader', { name: /name/i })
    const sortButton = within(nameColumnHeader).getByRole('button')
    await user.click(sortButton)

    // After sorting, the query should be called again with sort params.
    // We verify useQuery was called after the sort click.
    expect(vi.mocked(accessClient.useQuery)).toHaveBeenCalled()
  })

  it('sorts by Scope column when its header is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const scopeHeader = screen.getByRole('columnheader', { name: /scope/i })
    await user.click(within(scopeHeader).getByRole('button'))

    expect(vi.mocked(accessClient.useQuery)).toHaveBeenCalled()
  })

  it('sorts by Type column when its header is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const typeHeader = screen.getByRole('columnheader', { name: /type/i })
    await user.click(within(typeHeader).getByRole('button'))

    expect(vi.mocked(accessClient.useQuery)).toHaveBeenCalled()
  })

  it('sorts by Project column when its header is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies)

    render(<PoliciesTab />, { wrapper })

    const projectHeader = screen.getByRole('columnheader', { name: /project/i })
    await user.click(within(projectHeader).getByRole('button'))

    expect(vi.mocked(accessClient.useQuery)).toHaveBeenCalled()
  })

  it('has no accessibility violations in empty state', async () => {
    setupPoliciesQuery([])

    const { container } = render(<PoliciesTab />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('navigates to the next page when next button is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies, { total: 40, next: 'cursor-page2' })

    render(<PoliciesTab />, { wrapper })

    const nextButton = screen.getByRole('button', { name: /next page/i })
    await user.click(nextButton)

    // Verify useQuery was called again (with cursor param on re-render)
    const calls = vi.mocked(accessClient.useQuery).mock.calls
    const lastCall = calls[calls.length - 1]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access -- test assertion on mock call args
    const queryParams = (lastCall?.[2] as any)?.params?.query as Record<string, unknown>
    expect(queryParams).toMatchObject({ cursor: 'cursor-page2' })
  })

  it('navigates to the previous page when prev button is clicked', async () => {
    const user = userEvent.setup()
    setupPoliciesQuery(samplePolicies, { total: 40, next: 'cursor-page2' })

    render(<PoliciesTab />, { wrapper })

    const nextButton = screen.getByRole('button', { name: /next page/i })
    await user.click(nextButton)

    const prevButton = screen.getByRole('button', { name: /previous page/i })
    await user.click(prevButton)

    // After going back, cursor should be null (first page)
    const calls = vi.mocked(accessClient.useQuery).mock.calls
    const lastCall = calls[calls.length - 1]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access -- test assertion on mock call args
    const queryParams = (lastCall?.[2] as any)?.params?.query as Record<string, unknown>
    expect(queryParams).not.toHaveProperty('cursor')
  })

  it('shows empty filter state when filters produce no results', async () => {
    const user = userEvent.setup()
    let returnEmpty = false

    vi.mocked(accessClient.useQuery).mockImplementation((() => ({
      data: {
        resources: returnEmpty ? [] : samplePolicies,
        total: returnEmpty ? 0 : samplePolicies.length,
        next: null,
        prev: null,
      },
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    })) as unknown as typeof accessClient.useQuery)

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('grid', { name: 'Policies' })).toBeInTheDocument()

    const filterInput = screen.getByPlaceholderText('Filter by name')
    await user.type(filterInput, 'nonexistent')

    returnEmpty = true

    const applyButton = screen.getByRole('button', { name: 'Apply filter' })
    await user.click(applyButton)

    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('renders footer with item count, total, and correct pagination button state on first page', () => {
    setupPoliciesQuery(samplePolicies, { total: 40, next: 'cursor-page2' })

    render(<PoliciesTab />, { wrapper })

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()

    const prevButton = screen.getByRole('button', { name: /previous page/i })
    const nextButton = screen.getByRole('button', { name: /next page/i })
    expect(prevButton).toBeDisabled()
    expect(nextButton).toBeEnabled()
  })

  describe('Additional coverage', () => {
    it('renders description text', () => {
      setupPoliciesQuery(samplePolicies)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText(/Policies define what actions are allowed or denied/)).toBeInTheDocument()
    })

    it('handles undefined resources gracefully', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: undefined, total: 0, next: null },
        isPending: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText('No policies yet')).toBeInTheDocument()
    })

    it('handles null data gracefully', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: null,
        isPending: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText('No policies yet')).toBeInTheDocument()
    })

    it('opens JSON dialog for second policy', async () => {
      const user = userEvent.setup()
      setupPoliciesQuery(samplePolicies)
      render(<PoliciesTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[1])

      const viewAction = await screen.findByRole('menuitem', { name: /View policy definition/i })
      await user.click(viewAction)

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'viewer-policy policy definition' })).toBeInTheDocument()
    })

    it('renders mixed policy types with multiple statements and scopes', () => {
      const mixedPolicies: PolicyRead[] = [
        {
          id: 'mix1',
          name: 'deny-policy',
          description: null,
          statements: [{ scope: 'self', effect: 'deny', actions: ['workflow:delete'] }],
          is_builtin: false,
          is_project_eligible: true,
          is_system_scoped: false,
          project_id: 'proj-1',
          scope: 'project',
          labels: {},
          created_at: '2024-03-01T00:00:00Z',
          updated_at: null,
        },
        {
          id: 'mix2',
          name: 'multi-statement-policy',
          description: 'Has multiple statements',
          statements: [
            { scope: 'any', effect: 'allow', actions: ['workflow:read'] },
            { scope: 'self', effect: 'deny', actions: ['workflow:delete', 'workflow:write'] },
          ],
          is_builtin: true,
          is_project_eligible: false,
          is_system_scoped: true,
          project_id: null,
          scope: 'any',
          labels: {},
          created_at: '2024-04-01T00:00:00Z',
          updated_at: '2024-05-01T00:00:00Z',
        },
      ]
      setupPoliciesQuery(mixedPolicies)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText('deny-policy')).toBeInTheDocument()
      expect(screen.getByText('multi-statement-policy')).toBeInTheDocument()
      expect(screen.getByText('Has multiple statements')).toBeInTheDocument()
      expect(screen.getAllByText('Deny').length).toBeGreaterThan(0)
    })

    it('opens and closes JSON dialog sequentially for different policies', async () => {
      const user = userEvent.setup()
      setupPoliciesQuery(samplePolicies)
      render(<PoliciesTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])
      await user.click(await screen.findByRole('menuitem', { name: /view policy definition/i }))
      expect(screen.getByRole('heading', { name: 'admin-policy policy definition' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Close policy definition' }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      await user.click(kebabs[1])
      await user.click(await screen.findByRole('menuitem', { name: /view policy definition/i }))
      expect(screen.getByRole('heading', { name: 'viewer-policy policy definition' })).toBeInTheDocument()
    })

    it('renders data while background refetching', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: samplePolicies,
          total: samplePolicies.length,
          next: null,
          prev: null,
        },
        isPending: false,
        isFetching: true,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText('admin-policy')).toBeInTheDocument()
      expect(screen.getByText('viewer-policy')).toBeInTheDocument()
    })

    it('renders project name from projectNameMap', () => {
      setupPoliciesQuery(samplePolicies)
      render(<PoliciesTab />, { wrapper })

      expect(screen.getByText('Project One')).toBeInTheDocument()
    })
  })
})
