import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { expectPageTitle } from '../../../test/pageTitle'

import Credentials from './Credentials'

const { mockSelectedProject } = vi.hoisted(() => ({
  mockSelectedProject: { current: null as { id: string; name: string; is_builtin?: boolean } | null },
}))
const { mockAllProjectsRef } = vi.hoisted(() => ({
  mockAllProjectsRef: {
    current: [
      { id: 'proj-1', name: 'Project Alpha' },
      { id: 'proj-2', name: 'Project Beta' },
    ] as Array<{ id: string; name: string; is_builtin?: boolean }>,
  },
}))
const MockProjectSelector = () => <span>Mock Project Selector</span>

vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  integrationsClient: {
    useQuery: vi.fn(() => ({
      data: { resources: [] },
      isPending: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })),
  },

  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockProjects = [
  { id: 'proj-1', name: 'Project Alpha' },
  { id: 'proj-2', name: 'Project Beta' },
]

vi.mock('../../access/useAllProjects', () => {
  const projectsMock = () => ({
    projects: mockAllProjectsRef.current,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
  return { useAllProjects: projectsMock, useSelectableProjects: projectsMock }
})

vi.mock('../../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => ({
    selectedProject: mockSelectedProject.current,
    isAllProjects: mockSelectedProject.current === null,
    projects: mockProjects,
    ProjectSelector: <MockProjectSelector />,
  }),
}))

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/configuration/credentials',
}))

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

const { mockCredentialPermissions } = vi.hoisted(() => ({
  mockCredentialPermissions: {
    current: {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
      tooltips: {
        create: 'create tooltip',
        update: 'update tooltip',
        enable: 'enable tooltip',
        delete: 'delete tooltip',
      },
    },
  },
}))

vi.mock('./useCredentialPermissions', () => ({
  useCredentialPermissions: () => mockCredentialPermissions.current,
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockCredentials = [
  {
    id: '1',
    name: 'GitHub API Token',
    description: 'Token for GitHub API access',
    credential_type_id: 'type-1',
    inputs: { token: '$encrypted$' },
    enabled: true,
    labels: {},
    project_id: 'proj-1',
    created_at: '2026-03-01T05:00:00Z',
    updated_at: '2026-03-18T05:45:00Z',
    integration_count: 3,
  },
  {
    id: '2',
    name: 'Staging SSH',
    description: 'SSH key for staging',
    credential_type_id: 'type-2',
    inputs: { username: 'deploy', ssh_private_key: '$encrypted$' },
    enabled: false,
    labels: {},
    project_id: 'proj-2',
    created_at: '2026-03-05T05:30:00Z',
    updated_at: '2026-03-05T05:30:00Z',
  },
  {
    id: '3',
    name: 'No Description Cred',
    description: '',
    credential_type_id: 'type-1',
    inputs: { token: '$encrypted$' },
    enabled: true,
    labels: {},
    project_id: 'proj-1',
    created_at: '2026-03-10T10:00:00Z',
    updated_at: '2026-03-10T10:00:00Z',
  },
]

const mockTypes = [
  {
    id: 'type-1',
    name: 'HTTP Bearer Token',
    description: 'Bearer token',
    inputs: { fields: [{ id: 'token', label: 'Token', type: 'string', secret: true }], required: ['token'] },
    injectors: {},
    managed: true,
  },
  { id: 'type-2', name: 'SSH Key', description: 'SSH key', inputs: {}, injectors: {}, managed: true },
]

function mockQuery(resources: typeof mockCredentials, workflowsOverride?: { data?: unknown; error?: unknown }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (_method: string, path: string): any => {
    if (path === '/credentials') {
      return {
        data: { resources, next: null, prev: null, total: resources.length },
        isLoading: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      }
    }
    if (path === '/credential_types') {
      return { data: { resources: mockTypes }, isLoading: false, error: null }
    }
    if (path === '/credentials/{credential_id}/workflows') {
      return {
        data: workflowsOverride?.data ?? undefined,
        error: workflowsOverride?.error ?? null,
        isPending: false,
      }
    }
    return { data: null, isLoading: false, error: null }
  }
}

describe('Credentials', () => {
  const previousTz = process.env.TZ

  beforeAll(() => {
    // formatDate() uses local timezone; pin UTC so table date expectations are stable in CI and on developer machines.
    process.env.TZ = 'UTC'
  })

  afterAll(() => {
    if (previousTz === undefined) {
      delete process.env.TZ
    } else {
      process.env.TZ = previousTz
    }
  })

  let mockMutate: ReturnType<typeof vi.fn>
  let mockMutateAsync: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockMutate = vi.fn()
    mockMutateAsync = vi.fn().mockResolvedValue(undefined)
    mockSelectedProject.current = { id: 'proj-1', name: 'My Project' }
    mockAllProjectsRef.current = [
      { id: 'proj-1', name: 'Project Alpha' },
      { id: 'proj-2', name: 'Project Beta' },
    ]
    mockCredentialPermissions.current = {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
      tooltips: {
        create: 'create tooltip',
        update: 'update tooltip',
        enable: 'enable tooltip',
        delete: 'delete tooltip',
      },
    }

    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(mockCredentials))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as never)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Credentials />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders the page title', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText('Credentials')).toBeInTheDocument()
  })

  it('renders create credential button', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByRole('button', { name: 'Create credential' })).toBeInTheDocument()
  })

  it('renders credential names in the table', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText('GitHub API Token')).toBeInTheDocument()
    expect(screen.getByText('Staging SSH')).toBeInTheDocument()
  })

  it('renders credential descriptions in expandable rows (hidden by default)', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText('Token for GitHub API access')).toBeInTheDocument()
    expect(screen.queryByText('Token for GitHub API access')).not.toBeVisible()
  })

  it('has no accessibility violations when rows are expanded', async () => {
    const user = userEvent.setup()
    const { container } = render(<Credentials />, { wrapper })
    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders type names', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getAllByText('HTTP Bearer Token').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('SSH Key')).toBeInTheDocument()
  })

  it('renders table column headers', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText('Last modified')).toBeInTheDocument()
    expect(screen.getByText('State')).toBeInTheDocument()
  })

  it('renders empty state when no credentials exist', () => {
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery([]))
    render(<Credentials />, { wrapper })
    expect(screen.getByText('No credentials yet')).toBeInTheDocument()
    // Only the empty state CTA should exist — header button is hidden
    expect(screen.getAllByRole('button', { name: 'Create credential' })).toHaveLength(1)
  })

  it('renders footer with credential count', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('opens create modal when create button is clicked', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })
    await user.click(screen.getByRole('button', { name: 'Create credential' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders kebab actions column for each row', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getAllByRole('button', { name: /^Actions for / })).toHaveLength(3)
  })

  it('shows disable confirmation dialog when toggling enabled credential', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])

    expect(screen.getByText('Disable credential?')).toBeInTheDocument()
  })

  it('calls patch mutation to enable a disabled credential directly', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    // After sorting by -created_at, the disabled credential "Staging SSH" is at index 1
    await user.click(switches[1])

    expect(mockMutateAsync).toHaveBeenCalled()
  })

  it('renders loading state', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(credentialsClient.useQuery).mockImplementation((): any => ({
      data: undefined,
      isLoading: true,
      error: null,
      isFetching: true,
    }))

    render(<Credentials />, { wrapper })
    expect(screen.getByText('Credentials')).toBeInTheDocument()
  })

  it('navigates to credential detail when row is clicked', () => {
    render(<Credentials />, { wrapper })

    const link = screen.getByRole('link', { name: 'GitHub API Token' })
    expect(link).toHaveAttribute('href', '/configuration/credentials/1')
  })

  it('renders formatted dates in table cells', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText(/Mar 18, 2026/)).toBeInTheDocument()
    expect(screen.getByText(/Mar 1, 2026/)).toBeInTheDocument()
  })

  it('renders dash for workflows and last used columns', () => {
    render(<Credentials />, { wrapper })
    const dashes = screen.getAllByText('\u2014')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('renders type as dash when type not found', () => {
    const credWithUnknownType = [{ ...mockCredentials[0], credential_type_id: 'unknown-type' }]
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(credWithUnknownType))

    render(<Credentials />, { wrapper })
    const dashes = screen.getAllByText('\u2014')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('confirms disable and calls patch mutation with onSuccess', async () => {
    mockMutateAsync.mockResolvedValue(undefined)

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])

    expect(screen.getByText('Disable credential?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Disable credential' }))

    expect(mockMutateAsync).toHaveBeenCalled()
    expect(screen.queryByText('Disable credential?')).not.toBeInTheDocument()
  })

  it('handles disable mutation error', async () => {
    mockMutateAsync.mockRejectedValue(new Error('Server error'))

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])
    await user.click(screen.getByRole('button', { name: 'Disable credential' }))

    expect(mockMutateAsync).toHaveBeenCalled()
  })

  it('shows warning when workflow fetch fails in disable dialog', async () => {
    vi.mocked(credentialsClient.useQuery).mockImplementation(
      mockQuery(mockCredentials, { error: new Error('Network error') })
    )

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])

    await screen.findByText('Disable credential?')
    expect(screen.getByText(/Unable to check/)).toBeInTheDocument()
  })

  it('shows affected workflows in disable dialog', async () => {
    vi.mocked(credentialsClient.useQuery).mockImplementation(
      mockQuery(mockCredentials, { data: { resources: [{ id: 'wf-1', name: 'My Workflow' }] } })
    )

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])

    await screen.findByText('My Workflow')
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Workflows')).toBeInTheDocument()
    expect(within(dialog).getByText('1')).toBeInTheDocument()
  })

  it('enables credential directly without dialog', async () => {
    mockMutateAsync.mockResolvedValue(undefined)

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    // After sorting by -created_at, the disabled credential "Staging SSH" is at index 1
    await user.click(switches[1])

    expect(mockMutateAsync).toHaveBeenCalled()
    expect(screen.queryByText('Disable credential?')).not.toBeInTheDocument()
  })

  it('handles enable mutation error', async () => {
    mockMutateAsync.mockRejectedValue(new Error('Failed'))

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    // After sorting by -created_at, the disabled credential "Staging SSH" is at index 1
    await user.click(switches[1])

    expect(mockMutateAsync).toHaveBeenCalled()
  })

  it('optimistically flips the enable switch before the patch resolves', async () => {
    let resolvePatch!: (value: unknown) => void
    mockMutateAsync.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve
        })
    )

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    // Staging SSH starts disabled
    expect(switches[1]).not.toBeChecked()
    await user.click(switches[1])

    await waitFor(() => {
      expect(screen.getAllByRole('switch', { name: 'Enabled' })[1]).toBeChecked()
    })

    await act(async () => {
      resolvePatch(undefined)
      await Promise.resolve()
    })
  })

  it('closes create modal on close', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Create credential' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders total count when more results exist', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(credentialsClient.useQuery).mockImplementation((_method: string, path: string): any => {
      if (path === '/credentials') {
        return {
          data: { resources: mockCredentials, next: 'cursor-next', prev: null, total: 50 },
          isLoading: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        }
      }
      if (path === '/credential_types') {
        return { data: { resources: mockTypes }, isLoading: false, error: null }
      }
      return { data: null, isLoading: false, error: null }
    })

    render(<Credentials />, { wrapper })
    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
  })

  it('cancels disable dialog', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const switches = screen.getAllByRole('switch', { name: 'Enabled' })
    await user.click(switches[0])

    expect(screen.getByText('Disable credential?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Disable credential?')).not.toBeInTheDocument()
  })

  it('opens delete dialog and confirms deletion', async () => {
    mockMutate.mockImplementation((_args: unknown, callbacks: { onSuccess?: () => void; onSettled?: () => void }) => {
      callbacks.onSuccess?.()
      callbacks.onSettled?.()
    })

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
    await user.click(firstKebab)

    const deleteItem = await screen.findByRole('menuitem', { name: /Delete credential/ })
    await user.click(deleteItem)

    expect(screen.getByText('Delete credential?')).toBeInTheDocument()
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument()

    const dialog = screen.getByRole('dialog')
    // Check the acknowledgement checkbox before clicking Delete
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(within(dialog).getByRole('button', { name: 'Delete credential' }))
    expect(mockMutate).toHaveBeenCalled()
  })

  it('handles delete mutation error', async () => {
    mockMutate.mockImplementation(
      (_args: unknown, callbacks: { onError?: (e: unknown) => void; onSettled?: () => void }) => {
        callbacks.onError?.(new Error('Failed'))
        callbacks.onSettled?.()
      }
    )

    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
    await user.click(firstKebab)

    const deleteItem = await screen.findByRole('menuitem', { name: /Delete credential/ })
    await user.click(deleteItem)

    const dialog = screen.getByRole('dialog')
    // Check the acknowledgement checkbox before clicking Delete
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(within(dialog).getByRole('button', { name: 'Delete credential' }))
    expect(mockMutate).toHaveBeenCalled()
  })

  it('opens edit modal via kebab menu', async () => {
    const user = userEvent.setup()
    render(<Credentials />, { wrapper })

    const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
    await user.click(firstKebab)

    const editItem = await screen.findByRole('menuitem', { name: /Edit credential/ })
    await user.click(editItem)

    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders error state from query', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(credentialsClient.useQuery).mockImplementation((): any => ({
      data: undefined,
      isLoading: false,
      error: new Error('Server error'),
      isError: true,
      isFetching: false,
    }))

    render(<Credentials />, { wrapper })
    expect(screen.getByText('Credentials')).toBeInTheDocument()
  })

  it('renders project switcher in the header', () => {
    render(<Credentials />, { wrapper })
    expect(screen.getByText('Mock Project Selector')).toBeInTheDocument()
  })

  it('enables create credential button even when no project is selected', () => {
    mockSelectedProject.current = null
    render(<Credentials />, { wrapper })
    expect(screen.getByRole('button', { name: 'Create credential' })).toBeEnabled()
  })

  it('enables create credential button when a project is selected', () => {
    mockSelectedProject.current = { id: 'proj-1', name: 'My Project' }
    render(<Credentials />, { wrapper })
    expect(screen.getByRole('button', { name: 'Create credential' })).toBeEnabled()
  })

  it('includes project_id in query params when project is selected', () => {
    mockSelectedProject.current = { id: 'proj-1', name: 'My Project' }
    render(<Credentials />, { wrapper })

    // The credentialsClient.useQuery for /credentials should have been called with project_id
    const calls = vi.mocked(credentialsClient.useQuery).mock.calls
    const credentialsCalls = calls.filter((c) => c[1] === '/credentials')
    expect(credentialsCalls.length).toBeGreaterThan(0)
    const lastCall = credentialsCalls[credentialsCalls.length - 1]
    const queryParams = (lastCall[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params?.query
    expect(queryParams).toHaveProperty('project_id', 'proj-1')
  })

  it('does not include project_id in query params when all projects mode is active', () => {
    mockSelectedProject.current = null
    render(<Credentials />, { wrapper })

    const calls = vi.mocked(credentialsClient.useQuery).mock.calls
    const credentialsCalls = calls.filter((c) => c[1] === '/credentials')
    expect(credentialsCalls.length).toBeGreaterThan(0)
    const lastCall = credentialsCalls[credentialsCalls.length - 1]
    const queryParams = (lastCall[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params?.query
    expect(queryParams).not.toHaveProperty('project_id')
  })

  it('renders empty state when no credentials exist (with project selected)', () => {
    mockSelectedProject.current = { id: 'proj-1', name: 'Project Alpha' }
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery([]))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
    render(<Credentials />, { wrapper })

    expect(screen.getByText('No credentials yet')).toBeInTheDocument()
    // Only the empty state CTA should exist — header button is hidden
    expect(screen.getAllByRole('button', { name: 'Create credential' })).toHaveLength(1)
  })

  it('renders grouped table body when viewing all projects', () => {
    mockSelectedProject.current = null
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(mockCredentials))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
    render(<Credentials />, { wrapper })

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.getByText('Project Beta')).toBeInTheDocument()
    expect(screen.getByText('GitHub API Token')).toBeInTheDocument()
    expect(screen.getByText('Staging SSH')).toBeInTheDocument()

    // Count badge removed — page-local counts were misleading (AAP-85112)
    const alphaHeader = screen.getByRole('row', { name: /Project Alpha/ })
    expect(within(alphaHeader).queryByText('1')).not.toBeInTheDocument()
  })

  it('collapses and expands project group when header is clicked', async () => {
    const user = userEvent.setup()
    mockSelectedProject.current = null
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(mockCredentials))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
    render(<Credentials />, { wrapper })

    expect(screen.getByText('GitHub API Token')).toBeInTheDocument()

    await user.click(screen.getByText('Project Alpha'))
    expect(screen.queryByText('GitHub API Token')).not.toBeInTheDocument()

    await user.click(screen.getByText('Project Alpha'))
    expect(screen.getByText('GitHub API Token')).toBeInTheDocument()
  })

  it('shows "No project" label for credentials without a known project', () => {
    mockSelectedProject.current = null
    const credWithUnknownProject = [{ ...mockCredentials[0], project_id: 'unknown-id' }]
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(credWithUnknownProject))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
    render(<Credentials />, { wrapper })

    expect(screen.getByText('unknown-id')).toBeInTheDocument()
  })

  it('renders flat table body when a project is selected', () => {
    mockSelectedProject.current = { id: 'proj-1', name: 'Project Alpha' }
    vi.mocked(credentialsClient.useQuery).mockImplementation(mockQuery(mockCredentials))
    vi.mocked(credentialsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
    render(<Credentials />, { wrapper })

    expect(screen.queryByText('Project Alpha')).not.toBeInTheDocument()
    expect(screen.getByText('GitHub API Token')).toBeInTheDocument()
  })

  describe('Expandable rows', () => {
    it('descriptions are hidden by default and shown when row is expanded', async () => {
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      expect(screen.getByText('Token for GitHub API access')).not.toBeVisible()

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('Token for GitHub API access')).toBeVisible()
    })

    it('expand-all button expands all rows, clicking again collapses them', async () => {
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const expandAllButton = screen.getByRole('button', { name: /expand all/i })
      await user.click(expandAllButton)

      expect(screen.getByText('Token for GitHub API access')).toBeVisible()
      expect(screen.getByText('SSH key for staging')).toBeVisible()

      // Click the same toggle again to collapse all
      await user.click(screen.getByRole('button', { name: /expand all|collapse all/i }))

      expect(screen.getByText('Token for GitHub API access')).not.toBeVisible()
      expect(screen.getByText('SSH key for staging')).not.toBeVisible()
    })

    it('toggling a single row does not affect other rows', async () => {
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('Token for GitHub API access')).toBeVisible()
      expect(screen.getByText('SSH key for staging')).not.toBeVisible()
    })

    it('credentials without descriptions do not show expand toggle', () => {
      render(<Credentials />, { wrapper })

      expect(screen.getByText('No Description Cred')).toBeInTheDocument()
      // Only 2 expand buttons for the 2 credentials with descriptions (not 3)
      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      expect(expandButtons).toHaveLength(2)
    })
  })

  describe('Page title', () => {
    it('sets the browser tab title', () => {
      render(<Credentials />, { wrapper })
      expectPageTitle(['Credentials'])
    })
  })

  describe('builtin project protection', () => {
    it('disables Create credential button when selected project is builtin', () => {
      mockSelectedProject.current = { id: 'proj-1', name: 'Builtin Project', is_builtin: true }
      render(<Credentials />, { wrapper })
      const createBtn = screen.getByRole('button', { name: 'Create credential' })
      expect(createBtn).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Create credential button when selected project is builtin and canCreate is false', () => {
      mockSelectedProject.current = { id: 'proj-1', name: 'Builtin Project', is_builtin: true }
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canCreate: false }
      render(<Credentials />, { wrapper })
      const createBtn = screen.getByRole('button', { name: 'Create credential' })
      expect(createBtn).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Create credential button when canCreate is false and project is not builtin', () => {
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canCreate: false }
      render(<Credentials />, { wrapper })
      const createBtn = screen.getByRole('button', { name: 'Create credential' })
      expect(createBtn).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables edit and delete row actions when credential belongs to a builtin project', async () => {
      // Builtin row actions use selectedProject / grouping projects, not useAllProjects alone.
      mockSelectedProject.current = { id: 'proj-1', name: 'Project Alpha', is_builtin: true }
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(firstKebab)

      const editItem = await screen.findByRole('menuitem', { name: /Edit credential/ })
      const deleteItem = screen.getByRole('menuitem', { name: /Delete credential/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
      expect(deleteItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables edit with builtin tooltip even when canUpdate is false', async () => {
      mockSelectedProject.current = { id: 'proj-1', name: 'Project Alpha', is_builtin: true }
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canUpdate: false }
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(firstKebab)

      const editItem = await screen.findByRole('menuitem', { name: /Edit credential/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables delete with builtin tooltip even when canDelete is false', async () => {
      mockSelectedProject.current = { id: 'proj-1', name: 'Project Alpha', is_builtin: true }
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canDelete: false }
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(firstKebab)

      const deleteItem = await screen.findByRole('menuitem', { name: /Delete credential/ })
      expect(deleteItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables edit row action when canUpdate is false and project is not builtin', async () => {
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canUpdate: false }
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(firstKebab)

      const editItem = await screen.findByRole('menuitem', { name: /Edit credential/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables delete row action when canDelete is false and project is not builtin', async () => {
      mockCredentialPermissions.current = { ...mockCredentialPermissions.current, canDelete: false }
      const user = userEvent.setup()
      render(<Credentials />, { wrapper })

      const [firstKebab] = screen.getAllByRole('button', { name: /^Actions for / })
      await user.click(firstKebab)

      const deleteItem = await screen.findByRole('menuitem', { name: /Delete credential/ })
      expect(deleteItem).toHaveAttribute('aria-disabled', 'true')
    })
  })
})
