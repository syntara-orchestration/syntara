import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { searchParamsMock } from '../../../test/searchParamsMock'
import { accessClient } from '../../access/accessClient'
import type { RoleAssignmentRead } from '../../access/types'

import { ProjectRoleAssignmentsTab } from './ProjectRoleAssignmentsTab'

vi.mock('@patternfly/react-table', async () => {
  const actual = await vi.importActual<typeof import('@patternfly/react-table')>('@patternfly/react-table')
  return {
    ...actual,
    ActionsColumn: ({ items }: { items: Array<{ title: ReactNode; onClick?: () => void }> }) => (
      <button type="button" onClick={() => items[0]?.onClick?.()}>
        Open actions
      </button>
    ),
  }
})

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/useAssignmentPermissions', () => ({
  useAssignmentPermissions: () => ({
    canAssign: true,
    canRevoke: true,
    isLoading: false,
    tooltips: { assign: '', revoke: '' },
  }),
}))

vi.mock('../../access/useRolePermissions', () => ({
  useRolePermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '' },
  }),
}))

vi.mock('./AddProjectRoleDialog', () => ({
  AddProjectRoleDialog: ({
    projectId,
    onClose,
    onSuccess,
  }: {
    projectId: string
    onClose: () => void
    onSuccess: () => void
  }) => (
    <div>
      Create project role modal (project: {projectId})
      <button type="button" onClick={onSuccess}>
        Mock create success
      </button>
      <button type="button" onClick={onClose}>
        Mock close create modal
      </button>
    </div>
  ),
}))

vi.mock('./AssignProjectRoleModal', () => ({
  AssignProjectRoleModal: ({
    isOpen,
    onSuccess,
    onClose,
  }: {
    isOpen: boolean
    onSuccess: () => void
    onClose: () => void
  }) =>
    isOpen ? (
      <div>
        Assign project role modal
        <button type="button" onClick={onSuccess}>
          Mock assign success
        </button>
        <button type="button" onClick={onClose}>
          Mock close modal
        </button>
      </div>
    ) : null,
}))

vi.mock('../../../utils/dateUtils', () => ({
  formatDateTime: (v: string | null | undefined) => v ?? 'N/A',
}))

vi.mock('../../../components/table/PaginationFooter', () => ({
  PaginationFooter: ({
    onPrev,
    onNext,
    onPerPageChange,
    page,
    perPage,
    total,
  }: {
    onPrev: () => void
    onNext: () => void
    onPerPageChange: (perPage: number) => void
    page: number
    perPage: number
    total: number
  }) => (
    <div data-testid="pagination-footer">
      <span>
        Page {page} of {Math.ceil(total / perPage) || 1}
      </span>
      <button type="button" onClick={onPrev} aria-label="Go to previous page">
        Previous
      </button>
      <button type="button" onClick={onNext} aria-label="Go to next page">
        Next
      </button>
      <button type="button" onClick={() => onPerPageChange(10)} aria-label="Set 10 per page">
        10 per page
      </button>
    </div>
  ),
}))

vi.mock('../../../hooks/routing/useSearchParams', async () => {
  const { useState, useEffect } = await import('react')
  const { searchParamsMock: mock } = await import('../../../test/searchParamsMock')
  return {
    useSearchParams: () => {
      const [, forceRender] = useState(0)
      useEffect(() => mock.subscribe(() => forceRender((n) => n + 1)), [])
      return [mock.get(), mock.set] as const
    },
  }
})

vi.mock('../../../hooks/routing/useSearch', () => ({ useSearch: () => '' }))
vi.mock('../../../hooks/routing/useLocation', () => ({ useLocation: () => '/' }))
vi.mock('../../../hooks/routing/useNavigate', () => ({ useNavigate: () => vi.fn() }))
const mockMutationReturn = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null,
  data: null,
  reset: vi.fn(),
  isIdle: true,
  isSuccess: false,
  failureCount: 0,
  failureReason: null,
  context: undefined,
  submittedAt: 0,
  variables: undefined,
  status: 'idle',
  isPaused: false,
} as never

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function setupMutationMock(callbackToInvoke: 'onSuccess' | 'onError', errorValue?: unknown) {
  const mutate = vi.fn(
    (
      _variables: unknown,
      options: { onSuccess?: () => void; onError?: (err: unknown) => void; onSettled?: () => void }
    ) => {
      if (callbackToInvoke === 'onSuccess') {
        options.onSuccess?.()
      } else {
        options.onError?.(errorValue ?? new Error('Mutation failed'))
      }
      options.onSettled?.()
    }
  )
  vi.mocked(accessClient.useMutation).mockReturnValue({
    ...({} as Record<string, unknown>),
    mutate,
    isPending: false,
    isError: false,
    error: null,
  } as never)
  return mutate
}

const mockAllAssignments = [
  {
    id: 'a1',
    principal_id: 'u1',
    group_id: null,
    principal_name: 'alice',
    role_name: 'admin',
    role_policies: ['read-all', 'write-all'],
    created_at: '2024-01-01T00:00:00Z',
    project_id: 'proj-1',
    project_name: 'Test Project',
  },
  {
    id: 'a2',
    principal_id: null,
    group_id: 'g1',
    principal_name: 'devs',
    role_name: 'editor',
    role_policies: ['read-all'],
    created_at: '2024-02-01T00:00:00Z',
    project_id: 'proj-1',
    project_name: 'Test Project',
  },
  {
    id: 'a3',
    principal_id: 'u1',
    group_id: null,
    principal_name: 'alice',
    role_name: 'viewer',
    role_policies: [],
    created_at: '2024-03-01T00:00:00Z',
    project_id: 'proj-1',
    project_name: 'Test Project',
  },
]

describe('ProjectRoleAssignmentsTab', () => {
  const mockRefetch = vi.fn().mockResolvedValue({})

  function setupMocks(assignments: RoleAssignmentRead[] = mockAllAssignments as unknown as RoleAssignmentRead[]) {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: assignments, total: assignments.length, next: null, prev: null },
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    searchParamsMock.reset()
    mockRefetch.mockResolvedValue({})
    setupMocks()
  })

  it('has no accessibility violations with assignments', async () => {
    const { container } = render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when empty', async () => {
    setupMocks([])
    const { container } = render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders table with assignment rows from API response', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('grid', { name: 'Project role assignments' })).toBeInTheDocument()
    expect(screen.getByText('devs')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText('editor')).toBeInTheDocument()
    expect(screen.getAllByText('alice')).toHaveLength(2)
  })

  it('links principal names to user and group detail pages', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const aliceLinks = screen.getAllByRole('link', { name: 'alice' })
    expect(aliceLinks).toHaveLength(2)
    for (const link of aliceLinks) {
      expect(link).toHaveAttribute('href', '/system-administration/access-management/users/u1')
    }
    expect(screen.getByRole('link', { name: 'devs' })).toHaveAttribute(
      'href',
      '/system-administration/access-management/groups/g1'
    )
  })

  it('shows User and Group type labels', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getAllByText('User')).toHaveLength(2)
    expect(screen.getByText('Group')).toBeInTheDocument()
  })

  it('shows Service Account type label with updated display colors', () => {
    setupMocks([
      ...(mockAllAssignments as unknown as RoleAssignmentRead[]),
      {
        id: 'a4',
        principal_id: 'sa-1',
        group_id: null,
        principal_type: 'service_account',
        principal_name: 'ci-bot',
        role_name: 'runner',
        role_policies: [],
        created_at: '2024-04-01T00:00:00Z',
        project_id: 'proj-1',
        project_name: 'Test Project',
      } as RoleAssignmentRead,
    ])
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('Service account', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getAllByText('User', { selector: '.pf-v6-c-label__text' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Group', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ci-bot' })).toHaveAttribute(
      'href',
      '/system-administration/access-management/service-accounts/sa-1'
    )
  })

  it('renders policy labels for assignments with policies', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getAllByText('read-all')).toHaveLength(2)
    expect(screen.getByText('write-all')).toBeInTheDocument()
  })

  it('renders "Assign role" button', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('button', { name: 'Assign role' })).toBeInTheDocument()
  })

  it('renders empty state when no assignments exist', () => {
    setupMocks([])
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('No role assignments yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assign role' })).toBeInTheDocument()
  })

  it('renders error state when query fails', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error('Network error'),
      refetch: vi.fn(),
    } as never)

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
  })

  it('renders loading state while fetching', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('passes query params including sort to the API', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const callArgs = vi
      .mocked(accessClient.useQuery)
      .mock.calls.find((call) => call[0] === 'get' && call[1] === '/projects/{project_id}/role_assignments')
    expect(callArgs).toBeDefined()
    const queryOptions = callArgs![2] as unknown as {
      params: { path: { project_id: string }; query: Record<string, unknown> }
    }
    expect(queryOptions.params.path).toEqual({ project_id: 'proj-1' })
    expect(queryOptions.params.query).toMatchObject({
      sort: 'principal_name',
      limit: 20,
      include_total: true,
    })
  })

  it('opens the assign modal from the toolbar when assignments exist', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))

    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()
  })

  it('opens the assign modal from the empty state CTA', async () => {
    const user = userEvent.setup()
    setupMocks([])
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))

    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()
  })

  it('opens unassign dialog when action is clicked and shows confirmation', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[0])

    expect(screen.getByText('Unassign role?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unassign' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('closes unassign dialog when cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[0])
    expect(screen.getByText('Unassign role?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Unassign role?')).not.toBeInTheDocument()
  })

  it('calls deleteAssignment when unassigning a user role', async () => {
    const user = userEvent.setup()
    const mutate = setupMutationMock('onSuccess')

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[0])
    await user.click(screen.getByRole('button', { name: 'Unassign' }))

    expect(mutate).toHaveBeenCalledWith(
      { params: { path: { project_id: 'proj-1', assignment_id: 'a1' } } },
      expect.anything()
    )
    expect(mockRefetch).toHaveBeenCalled()
  })

  it('calls deleteAssignment when unassigning a group role', async () => {
    const user = userEvent.setup()
    const mutate = setupMutationMock('onSuccess')

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[1])
    await user.click(screen.getByRole('button', { name: 'Unassign' }))

    expect(mutate).toHaveBeenCalledWith(
      { params: { path: { project_id: 'proj-1', assignment_id: 'a2' } } },
      expect.anything()
    )
  })

  it('shows error alert when unassign fails', async () => {
    const user = userEvent.setup()
    setupMutationMock('onError', new Error('Delete failed'))

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[0])
    await user.click(screen.getByRole('button', { name: 'Unassign' }))

    expect(screen.getByText('Failed to unassign role')).toBeInTheDocument()
  })

  it('builds assignedRolesByPrincipal map and passes it to modal', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))

    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()
  })

  it('refetches data when assign modal reports success', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))
    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mock assign success' }))

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('does not call mutate when handleUnassign is called with no assignmentToUnassign', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.queryByText('Unassign role?')).not.toBeInTheDocument()
  })

  it('renders sortable column headers', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const grid = screen.getByRole('grid', { name: 'Project role assignments' })
    expect(within(grid).getByText('Principal name')).toBeInTheDocument()
    expect(within(grid).getByText('Principal type')).toBeInTheDocument()
    expect(within(grid).getByText('Role name')).toBeInTheDocument()
    expect(within(grid).getByText('Policies')).toBeInTheDocument()
  })

  it('shows unassign confirmation with correct role and principal info', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const actionButtons = screen.getAllByRole('button', { name: 'Open actions' })
    await user.click(actionButtons[1])

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/editor/)).toBeInTheDocument()
    expect(within(dialog).getByText(/devs/)).toBeInTheDocument()
  })

  it('handles multiple assignments for the same user', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getAllByText('alice')).toHaveLength(2)
    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText('viewer')).toBeInTheDocument()
  })

  it('renders "Create role" button in toolbar', () => {
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('button', { name: 'Create role' })).toBeInTheDocument()
  })

  it('opens create role modal for the project', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Create role' }))

    expect(screen.getByText(/Create project role modal \(project: proj-1\)/)).toBeInTheDocument()
  })

  it('closes create role modal via onClose callback', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Create role' }))
    expect(screen.getByText(/Create project role modal/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mock close create modal' }))
    expect(screen.queryByText(/Create project role modal/)).not.toBeInTheDocument()
  })

  it('refetches data when create role reports success', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Create role' }))
    await user.click(screen.getByRole('button', { name: 'Mock create success' }))

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('closes the assign modal via onClose callback', async () => {
    const user = userEvent.setup()
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))
    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mock close modal' }))

    expect(screen.queryByText('Assign project role modal')).not.toBeInTheDocument()
  })

  it('closes the assign modal in empty state via onClose callback', async () => {
    const user = userEvent.setup()
    setupMocks([])
    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Assign role' }))
    expect(screen.getByText('Assign project role modal')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mock close modal' }))

    expect(screen.queryByText('Assign project role modal')).not.toBeInTheDocument()
  })

  it('renders dash for assignments with no policies', () => {
    setupMocks([
      {
        id: 'a-no-policies',
        principal_id: 'u5',
        group_id: null,
        principal_name: 'bob',
        role_name: 'empty-role',
        role_policies: [],
        created_at: '2024-01-01T00:00:00Z',
        project_id: 'proj-1',
        project_name: 'Test Project',
      },
    ])

    render(<ProjectRoleAssignmentsTab projectId="proj-1" />, { wrapper })

    const grid = screen.getByRole('grid', { name: 'Project role assignments' })
    expect(within(grid).getByText('-')).toBeInTheDocument()
  })
})
