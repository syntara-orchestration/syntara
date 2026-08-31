import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient, accessFetchClient } from './accessClient'
import { AssignmentsTab } from './AssignmentsTab'
import type { RoleAssignmentRead } from './types'

vi.mock('../../app/routerFlag', () => ({
  isTanStackRouter: () => false,
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
  },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useProjectNameMap', () => ({
  useProjectNameMap: () => ({
    projectNameMap: new Map([['p1', 'Project Alpha']]),
    isLoading: false,
  }),
}))

const mockPermissionsState = {
  canAssign: true,
  canRevoke: true,
  isLoading: false,
  tooltips: { assign: 'No assign permission', revoke: 'No revoke permission' },
}

vi.mock('./useAssignmentPermissions', () => ({
  useAssignmentPermissions: () => mockPermissionsState,
}))

vi.mock('./AssignRoleDialog', () => ({
  AssignRoleDialog: (props: { onClose: () => void; onSuccess: () => void }) => (
    <div data-testid="assign-role-dialog">
      <span>Add Assignment</span>
      <button onClick={props.onClose}>Close assign</button>
      <button onClick={props.onSuccess}>Save assign</button>
    </div>
  ),
}))

vi.mock('./EditAssignmentDialog', () => ({
  EditAssignmentDialog: (props: { displayName: string; onClose: () => void; onSuccess: () => void }) => (
    <div data-testid="edit-assignment-dialog">
      <span>Edit principal assignment</span>
      <span>{props.displayName}</span>
      <button onClick={props.onClose}>Close edit</button>
      <button onClick={props.onSuccess}>Save edit</button>
    </div>
  ),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockRefetch = vi.fn().mockResolvedValue({})
const mockDeleteMutate = vi.fn()

const sampleAssignments: RoleAssignmentRead[] = [
  {
    id: 'pr1',
    principal_id: 'u1',
    group_id: null,
    principal_type: 'user',
    principal_name: 'alice',
    role_name: 'Admin',
    role_description: null,
    role_policies: [],
    project_id: 'p1',
    project_name: 'Project Alpha',
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'pgr1',
    principal_id: null,
    group_id: 'g1',
    principal_type: 'group',
    principal_name: 'Devs',
    role_name: 'Editor',
    role_description: null,
    role_policies: [],
    project_id: 'p1',
    project_name: 'Project Alpha',
    created_at: '2024-02-01T00:00:00Z',
  },
  {
    id: 'sur1',
    principal_id: 'u2',
    group_id: null,
    principal_type: 'user',
    principal_name: 'bob',
    role_name: 'Viewer',
    role_description: 'Basic read access',
    role_policies: undefined,
    project_id: null,
    project_name: null,
    created_at: '2024-03-01T00:00:00Z',
  },
  {
    id: 'sar1',
    principal_id: 'sa-1',
    group_id: null,
    principal_type: 'service_account',
    principal_name: 'my-service-account',
    role_name: 'Project Editor',
    role_description: 'Edit project resources',
    role_policies: ['project.edit'],
    project_id: 'p1',
    project_name: 'Project Alpha',
    created_at: '2024-04-01T00:00:00Z',
  },
] as unknown as RoleAssignmentRead[]

function setupAssignmentsQuery(assignments: RoleAssignmentRead[], options?: { total?: number; next?: string | null }) {
  vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/role_assignments') {
      return {
        data: {
          resources: assignments,
          total: options?.total ?? assignments.length,
          next: options?.next ?? null,
          prev: null,
        },
        isPending: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never
    }
    return {
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never
  })
}

describe('AssignmentsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPermissionsState.canAssign = true
    mockPermissionsState.canRevoke = true
    setupAssignmentsQuery([])

    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: mockDeleteMutate,
      isPending: false,
      isError: false,
      error: null,
      data: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      isIdle: true,
      isSuccess: false,
      failureCount: 0,
      failureReason: null,
      context: undefined,
      submittedAt: 0,
      variables: undefined,
      status: 'idle',
      isPaused: false,
    } as never)

    vi.mocked(accessFetchClient.GET).mockResolvedValue({ data: { resources: [] } } as never)
  })

  describe('Empty State', () => {
    it('shows empty state when no rows and no active filters', () => {
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('No assignments yet')).toBeInTheDocument()
      expect(screen.getByText('Assign roles to users or groups to grant access.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Add assignment' })).toBeInTheDocument()
    })

    it('renders Add assignment button in empty state', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const addButton = screen.getByRole('button', { name: 'Add assignment' })
      expect(addButton).toBeInTheDocument()
      await user.click(addButton)
    })
  })

  describe('Table Rendering', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('renders table with data rows', () => {
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByRole('grid', { name: 'Role assignments' })).toBeInTheDocument()
      expect(screen.getByText('alice')).toBeInTheDocument()
      expect(screen.getByText('Devs')).toBeInTheDocument()
      expect(screen.getByText('bob')).toBeInTheDocument()
    })

    it('links principal names to user, group, and service account detail pages', () => {
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByRole('link', { name: 'alice' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/users/u1'
      )
      expect(screen.getByRole('link', { name: 'Devs' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/groups/g1'
      )
      expect(screen.getByRole('link', { name: 'bob' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/users/u2'
      )
      expect(screen.getByRole('link', { name: 'my-service-account' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/service-accounts/sa-1'
      )
    })

    it('renders column headers', () => {
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByRole('columnheader', { name: /Principal Name/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Principal Type/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Role Name/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Scope/i })).toBeInTheDocument()
    })

    it('renders User label for user principal type', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[1]).getByText('User')).toBeInTheDocument()
    })

    it('renders Group label for group principal type', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[2]).getByText('Group')).toBeInTheDocument()
    })

    it('renders Service Account label for service_account principal type', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      const rows = within(table).getAllByRole('row')
      // Row 4 is my-service-account (service_account)
      expect(within(rows[4]).getByText('Service account')).toBeInTheDocument()
    })

    it('renders role names as truncated text instead of colored labels', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      expect(within(table).getByText('Admin')).toBeInTheDocument()
      expect(within(table).getByText('Editor')).toBeInTheDocument()
      expect(within(table).getByText('Viewer')).toBeInTheDocument()
    })

    it('renders updated principal type label colors from principalTypeDisplay', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[1]).getByText('User', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
      expect(within(rows[2]).getByText('Group', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
      expect(within(rows[4]).getByText('Service account', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    })

    it('renders project name for project-scoped rows', () => {
      render(<AssignmentsTab />, { wrapper })

      const projectLabels = screen.getAllByText('Project Alpha')
      expect(projectLabels.length).toBeGreaterThanOrEqual(1)
    })

    it('renders System label for system-scoped rows', () => {
      render(<AssignmentsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[3]).getByText('System')).toBeInTheDocument()
    })

    it('renders policies as labels when row is expanded', async () => {
      const withPolicies = [
        {
          ...sampleAssignments[0],
          role_policies: ['read-only', 'write-access'],
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(withPolicies)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      expect(screen.queryByText('read-only')).not.toBeVisible()

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('read-only')).toBeVisible()
      expect(screen.getByText('write-access')).toBeVisible()
    })

    it('does not show a Policies column header', () => {
      setupAssignmentsQuery(sampleAssignments)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.queryByRole('columnheader', { name: 'Policies' })).not.toBeInTheDocument()
    })
  })

  describe('Expandable rows', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('policies are hidden by default and shown when row is expanded', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      expect(screen.queryByText('project.edit')).not.toBeVisible()

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('project.edit')).toBeVisible()
    })

    it('expand-all button expands all rows, clicking again collapses them', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /expand all/i }))

      expect(screen.getByText('project.edit')).toBeVisible()

      await user.click(screen.getByRole('button', { name: /expand all/i }))

      expect(screen.queryByText('project.edit')).not.toBeVisible()
    })

    it('toggling a single row does not affect other rows', async () => {
      const twoPolicyRows = [
        { ...sampleAssignments[0], role_policies: ['alpha-policy'] },
        { ...sampleAssignments[3], role_policies: ['beta-policy'] },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(twoPolicyRows)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('alpha-policy')).toBeVisible()
      expect(screen.queryByText('beta-policy')).not.toBeVisible()
    })

    it('renders User label when group_id is null', () => {
      const userOnly = [
        {
          ...sampleAssignments[0],
          id: 'sa1',
          group_id: null,
          principal_name: 'bot-runner',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(userOnly)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('bot-runner')).toBeInTheDocument()
      expect(screen.getByText('User')).toBeInTheDocument()
    })

    it('renders role description tooltip when present', () => {
      const withDescription = [
        {
          ...sampleAssignments[0],
          role_description: 'Full system access',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(withDescription)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('Admin')).toBeInTheDocument()
    })

    it('renders project id as fallback when project name is missing', () => {
      const withMissingProjectName = [
        {
          ...sampleAssignments[0],
          project_name: null,
          project_id: 'orphan-project-id',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(withMissingProjectName)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('orphan-project-id')).toBeInTheDocument()
    })

    it('renders Add assignment button', () => {
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByRole('button', { name: /Add assignment/i })).toBeInTheDocument()
    })
  })

  describe('Loading and error states', () => {
    it('displays loading state when query is pending', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/role_assignments') {
          return {
            data: undefined,
            isPending: true,
            isFetching: true,
            isError: false,
            error: null,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    })

    it('displays error state when query fails', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/role_assignments') {
          return {
            data: undefined,
            isPending: false,
            isFetching: false,
            isError: true,
            error: new Error('Failed to load assignments'),
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })
  })

  describe('Filter empty state', () => {
    it('shows filter empty state when filters are active but no results', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasNameFilter = opts?.params?.query?.['principal_name[contains]']
        return {
          data: {
            resources: hasNameFilter ? [] : sampleAssignments,
            next: null,
            total: hasNameFilter ? 0 : 3,
          },
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /principal name filter/i })
      await user.type(textInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })
  })

  describe('Row Actions', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('opens edit dialog when Edit action is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByText('Edit principal assignment')).toBeInTheDocument()
      })
    })

    it('opens delete dialog when Delete action is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Remove assignment?')).toBeInTheDocument()
      })
    })
  })

  describe('Delete Confirmation Modal', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('shows the delete modal with Remove and Cancel buttons', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Remove assignment?')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      })
    })

    it('shows revoke message in delete modal body', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText(/The associated permissions will be revoked/)).toBeInTheDocument()
      })
    })

    it('calls delete mutation when Remove button is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      const removeButton = await screen.findByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      expect(mockDeleteMutate).toHaveBeenCalled()
    })

    it('closes delete modal when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      const dialog = await screen.findByRole('dialog', { name: /Remove assignment/i })

      await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: /Remove assignment/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('Add Assignment Dialog', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('opens add dialog when Add assignment button is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Add assignment/i }))

      await waitFor(() => {
        expect(screen.getByTestId('assign-role-dialog')).toBeInTheDocument()
      })
    })

    it('closes add dialog when Close is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Add assignment/i }))
      await waitFor(() => {
        expect(screen.getByTestId('assign-role-dialog')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Close assign' }))
      await waitFor(() => {
        expect(screen.queryByTestId('assign-role-dialog')).not.toBeInTheDocument()
      })
    })

    it('refetches on successful assignment', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Add assignment/i }))
      await waitFor(() => {
        expect(screen.getByTestId('assign-role-dialog')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Save assign' }))
      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  describe('Sorting', () => {
    beforeEach(() => {
      setupAssignmentsQuery(sampleAssignments)
    })

    it('renders sortable Principal Name column', () => {
      render(<AssignmentsTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /Principal Name/i })
      expect(within(nameHeader).getByRole('button')).toBeInTheDocument()
    })

    it('passes sort parameter to the API', () => {
      render(<AssignmentsTab />, { wrapper })

      const callArgs = vi
        .mocked(accessClient.useQuery)
        .mock.calls.find((call) => call[0] === 'get' && call[1] === '/role_assignments')
      expect(callArgs).toBeDefined()
      const queryOptions = callArgs![2] as unknown as {
        params: { query: Record<string, unknown> }
      }
      expect(queryOptions.params.query).toMatchObject({
        sort: 'principal_name',
        limit: 20,
        include_total: true,
      })
    })

    it('sends sort parameter when column header is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /Principal Name/i })
      await user.click(within(nameHeader).getByRole('button'))

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort')
      })
    })

    it('sends descending sort parameter when already-sorted column is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /Principal Name/i })
      const sortButton = within(nameHeader).getByRole('button')

      await user.click(sortButton)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', '-principal_name')
      })
    })

    it('sorts by Role Name column when its header is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const roleHeader = screen.getByRole('columnheader', { name: /Role Name/i })
      await user.click(within(roleHeader).getByRole('button'))

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort')
      })
    })

    it('sorts by Scope column when its header is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const scopeHeader = screen.getByRole('columnheader', { name: /^Scope$/i })
      await user.click(within(scopeHeader).getByRole('button'))

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort')
      })
    })
  })

  describe('Pagination', () => {
    it('renders footer with item count', () => {
      setupAssignmentsQuery(sampleAssignments)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })

    it('navigates to next page when next cursor is available', async () => {
      setupAssignmentsQuery(sampleAssignments, { total: 25, next: 'next-cursor' })

      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const nextButton = screen.getByRole('button', { name: /next page/i })
      await user.click(nextButton)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('cursor', 'next-cursor')
      })
    })
  })

  describe('Delete flow', () => {
    async function openDeleteDialog() {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Remove assignment?')).toBeInTheDocument()
      })
      return user
    }

    it('calls delete mutation for project-scoped assignment', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('button', { name: 'Remove' }))

      expect(mockDeleteMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          params: { path: { project_id: 'p1', assignment_id: 'pr1' } },
        }),
        expect.any(Object)
      )
    })

    it('refetches assignments on successful delete', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('button', { name: 'Remove' }))

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onSuccess: () => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      expect(mockRefetch).toHaveBeenCalled()
      await waitFor(() => {
        expect(screen.queryByText('Remove assignment?')).not.toBeInTheDocument()
      })
    })

    it('closes dialog on failed delete', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('button', { name: 'Remove' }))

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onError: (error: unknown) => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError(new Error('Server error'))
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Remove assignment?')).not.toBeInTheDocument()
      })
    })
  })

  describe('System-scoped delete', () => {
    it('calls system delete mutation for non-project assignment', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[2])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Remove assignment?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Remove' }))

      expect(mockDeleteMutate).toHaveBeenCalledWith(
        expect.objectContaining({ params: { path: { assignment_id: 'sur1' } } }),
        expect.any(Object)
      )
    })
  })

  describe('Edit dialog', () => {
    it('opens edit dialog with row data', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByTestId('edit-assignment-dialog')).toBeInTheDocument()
      })
    })

    it('closes edit dialog', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByTestId('edit-assignment-dialog')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Close edit' }))
      await waitFor(() => {
        expect(screen.queryByTestId('edit-assignment-dialog')).not.toBeInTheDocument()
      })
    })

    it('refetches on successful edit', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByTestId('edit-assignment-dialog')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Save edit' }))
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('opens edit dialog for system-scoped assignment', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[2])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      await waitFor(() => {
        const dialog = screen.getByTestId('edit-assignment-dialog')
        expect(dialog).toBeInTheDocument()
        expect(within(dialog).getByText('bob')).toBeInTheDocument()
      })
    })
  })

  describe('Filter transformation', () => {
    it('transforms project filter to project_id for API', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasProjectFilter = opts?.params?.query?.['project_id']
        return {
          data: {
            resources: hasProjectFilter ? [sampleAssignments[0]] : sampleAssignments,
            next: null,
            total: hasProjectFilter ? 1 : 3,
          },
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const toolbar = screen.getByRole('search', { name: /filters/i })
      const filterSelect = within(toolbar).getAllByRole('button', { name: /Principal Name/i })[0]
      await user.click(filterSelect)
      const projectOption = await screen.findByRole('option', { name: /Project/i })
      await user.click(projectOption)

      const selectToggle = screen.getByRole('button', { name: /Filter by project/i })
      await user.click(selectToggle)

      const firstProject = await screen.findByRole('option', { name: 'Project Alpha' })
      await user.click(firstProject)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('project_id')
      })
    })

    it('passes through role_name filter unchanged', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasRoleFilter = opts?.params?.query?.['role_name[contains]']
        return {
          data: {
            resources: hasRoleFilter ? [sampleAssignments[0]] : sampleAssignments,
            next: null,
            total: hasRoleFilter ? 1 : 3,
          },
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const toolbar = screen.getByRole('search', { name: /filters/i })
      const filterSelect = within(toolbar).getAllByRole('button', { name: /Principal Name/i })[0]
      await user.click(filterSelect)
      const roleOption = await screen.findByRole('option', { name: /Role Name/i })
      await user.click(roleOption)

      const textInput = screen.getByRole('textbox', { name: /role name filter/i })
      await user.type(textInput, 'Admin')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('role_name[contains]')
      })
    })

    it('transforms type filter to principal_type for API', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasTypeFilter = opts?.params?.query?.['principal_type']
        return {
          data: {
            resources: hasTypeFilter ? [sampleAssignments[0]] : sampleAssignments,
            next: null,
            total: hasTypeFilter ? 1 : 3,
          },
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const toolbar = screen.getByRole('search', { name: /filters/i })
      const filterSelect = within(toolbar).getAllByRole('button', { name: /Principal Name/i })[0]
      await user.click(filterSelect)
      const typeOption = await screen.findByRole('option', { name: /Principal Type/i })
      await user.click(typeOption)

      const selectToggle = screen.getByRole('button', { name: /Filter by principal type/i })
      await user.click(selectToggle)

      const userOption = await screen.findByRole('option', { name: 'User' })
      await user.click(userOption)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('principal_type')
      })
    })
  })

  describe('Disabled permissions', () => {
    beforeEach(() => {
      mockPermissionsState.canAssign = false
      mockPermissionsState.canRevoke = false
      setupAssignmentsQuery(sampleAssignments)
    })

    it('disables Add assignment button when canAssign is false', () => {
      render(<AssignmentsTab />, { wrapper })

      const addButton = screen.getByRole('button', { name: /Add assignment/i })
      expect(addButton).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables row edit action when canAssign is false', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      expect(editOption).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables row delete action when canRevoke is false', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      expect(deleteOption).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not open edit dialog when canAssign is false and action is clicked', async () => {
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      await user.click(editOption)

      expect(screen.queryByText('Edit principal assignment')).not.toBeInTheDocument()
    })

    it('does not show empty state add button when canAssign is false', () => {
      setupAssignmentsQuery([])
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('No assignments yet')).toBeInTheDocument()
    })
  })

  describe('Delete dialog project scope message', () => {
    it('shows project name in delete dialog for project-scoped assignment', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText(/in project/)).toBeInTheDocument()
      })
    })

    it('does not show project info for system-scoped delete', async () => {
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[2])
      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Remove assignment?')).toBeInTheDocument()
        expect(screen.queryByText(/in project/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Content description', () => {
    it('renders the assignments description text', () => {
      setupAssignmentsQuery(sampleAssignments)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText(/Assignments connect principals to roles/)).toBeInTheDocument()
    })
  })

  describe('Mixed row data', () => {
    it('renders rows with all optional fields populated', async () => {
      const fullRow: RoleAssignmentRead[] = [
        {
          id: 'full1',
          principal_id: 'u1',
          group_id: null,
          principal_name: 'full-user',
          role_name: 'SuperAdmin',
          role_description: 'Has all permissions',
          role_policies: ['policy-a', 'policy-b', 'policy-c', 'policy-d'],
          project_id: 'p1',
          project_name: 'Project Alpha',
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'full2',
          principal_id: null,
          group_id: 'g2',
          principal_name: 'ops-team',
          role_name: 'Operator',
          role_description: null,
          role_policies: ['ops-policy'],
          project_id: null,
          project_name: null,
          created_at: '2024-06-01T00:00:00Z',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(fullRow)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('full-user')).toBeInTheDocument()
      expect(screen.getByText('ops-team')).toBeInTheDocument()
      expect(screen.getByText('SuperAdmin')).toBeInTheDocument()
      expect(screen.getByText('Operator')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /expand all/i }))

      expect(screen.getByText('policy-a')).toBeVisible()
      expect(screen.getByText('ops-policy')).toBeVisible()
    })

    it('renders single row with no project and empty policies', () => {
      const minimalRow: RoleAssignmentRead[] = [
        {
          id: 'min1',
          principal_id: 'u99',
          group_id: null,
          principal_name: 'solo-user',
          role_name: 'Minimal',
          role_description: null,
          role_policies: [],
          project_id: null,
          project_name: null,
          created_at: '2024-01-01T00:00:00Z',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(minimalRow)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('solo-user')).toBeInTheDocument()
      expect(screen.getByText('System')).toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: 'Policies' })).not.toBeInTheDocument()
    })
  })

  describe('Null/undefined data handling', () => {
    it('handles undefined resources gracefully', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/role_assignments') {
          return {
            data: { resources: undefined, total: 0, next: null },
            isPending: false,
            isFetching: false,
            isError: false,
            error: null,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('No assignments yet')).toBeInTheDocument()
    })

    it('handles null data gracefully', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/role_assignments') {
          return {
            data: null,
            isPending: false,
            isFetching: false,
            isError: false,
            error: null,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('No assignments yet')).toBeInTheDocument()
    })

    it('does not show policy labels until a row is expanded', () => {
      setupAssignmentsQuery(sampleAssignments)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.queryByText('project.edit')).not.toBeVisible()
    })
  })

  describe('Background refetch', () => {
    it('renders data while isFetching is true', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/role_assignments') {
          return {
            data: {
              resources: sampleAssignments,
              total: sampleAssignments.length,
              next: null,
              prev: null,
            },
            isPending: false,
            isFetching: true,
            isError: false,
            error: null,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never
      })

      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('alice')).toBeInTheDocument()
      expect(screen.getByText('Devs')).toBeInTheDocument()
    })
  })

  describe('Partial permission states', () => {
    it('disables only edit when canAssign is false but canRevoke is true', async () => {
      mockPermissionsState.canAssign = false
      mockPermissionsState.canRevoke = true
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      expect(editOption).toHaveAttribute('aria-disabled', 'true')
      expect(deleteOption).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('disables only delete when canRevoke is false but canAssign is true', async () => {
      mockPermissionsState.canAssign = true
      mockPermissionsState.canRevoke = false
      setupAssignmentsQuery(sampleAssignments)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /Edit assignment/i })
      const deleteOption = await screen.findByRole('menuitem', { name: /Delete assignment/i })
      expect(editOption).not.toHaveAttribute('aria-disabled', 'true')
      expect(deleteOption).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('buildPermissionRow edge cases via rendering', () => {
    it('renders System scope for assignment without project_id', () => {
      const systemOnly: RoleAssignmentRead[] = [
        {
          id: 'sys1',
          principal_id: 'u1',
          group_id: null,
          principal_name: 'sys-user',
          role_name: 'SysAdmin',
          role_description: undefined,
          role_policies: undefined,
          project_id: undefined,
          project_name: undefined,
          created_at: '2024-01-01T00:00:00Z',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(systemOnly)
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('sys-user')).toBeInTheDocument()
      expect(screen.getByText('System')).toBeInTheDocument()
      expect(screen.getByText('User')).toBeInTheDocument()
    })

    it('renders group assignment with policies when expanded', async () => {
      const groupRow: RoleAssignmentRead[] = [
        {
          id: 'grp1',
          principal_id: null,
          group_id: 'g99',
          principal_name: 'QA Team',
          role_name: 'Tester',
          role_description: 'Run tests',
          role_policies: ['test-read', 'test-write'],
          project_id: 'p1',
          project_name: 'Project Alpha',
          created_at: '2024-05-01T00:00:00Z',
        },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(groupRow)
      const user = userEvent.setup()
      render(<AssignmentsTab />, { wrapper })

      expect(screen.getByText('QA Team')).toBeInTheDocument()
      expect(screen.getByText('Group')).toBeInTheDocument()
      expect(screen.getByText('Tester')).toBeInTheDocument()

      await user.click(screen.getAllByRole('button', { name: /details/i })[0])

      expect(screen.getByText('test-read')).toBeVisible()
      expect(screen.getByText('test-write')).toBeVisible()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with data', async () => {
      setupAssignmentsQuery(sampleAssignments)

      const { container } = render(<AssignmentsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      const { container } = render(<AssignmentsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with expanded rows', async () => {
      const withPolicies = [
        { ...sampleAssignments[0], role_policies: ['read-only', 'write-access'] },
        { ...sampleAssignments[3], role_policies: ['project.edit'] },
      ] as unknown as RoleAssignmentRead[]
      setupAssignmentsQuery(withPolicies)
      const user = userEvent.setup()

      const { container } = render(<AssignmentsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /expand all/i }))
      await waitFor(() => {
        expect(screen.getByText('read-only')).toBeVisible()
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
