import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'
import { searchParamsMock } from '../../test/searchParamsMock'
import { accessClient } from '../access/accessClient'
import { useAllProjects, useSelectableProjects } from '../access/useAllProjects'
import { useAllRoles } from '../access/useAllRoles'

import { RoleAssignmentsPanel } from './RoleAssignmentsPanel'

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/useAllRoles', () => ({
  useAllRoles: vi.fn(),
}))

vi.mock('../access/useAllProjects', () => ({
  useAllProjects: vi.fn(),
  useSelectableProjects: vi.fn(),
}))

vi.mock('../access/useAssignmentPermissions', () => ({
  useAssignmentPermissions: () => ({
    canAssign: true,
    canRevoke: true,
    isLoading: false,
    tooltips: { assign: '', revoke: '' },
  }),
}))

vi.mock('../access/useAlreadyAssignedRoles', () => ({
  useAlreadyAssignedRoles: () => ({ assigned: new Set<string>(), isLoading: false, isError: false }),
  roleAssignmentsQueryKey: (...args: unknown[]) => ['role-assignments', ...args],
  PRINCIPAL_ID_FIELD: { user: 'userId', group: 'groupId', service_account: 'serviceAccountId' },
}))

vi.mock('../../hooks/routing/useSearchParams', async () => {
  const { useState, useEffect } = await import('react')
  const { searchParamsMock: mock } = await import('../../test/searchParamsMock')
  return {
    useSearchParams: () => {
      const [, forceRender] = useState(0)
      useEffect(() => mock.subscribe(() => forceRender((n) => n + 1)), [])
      return [mock.get(), mock.set] as const
    },
  }
})

vi.mock('../../hooks/routing/useSearch', () => ({ useSearch: () => '' }))
vi.mock('../../hooks/routing/useLocation', () => ({ useLocation: () => '/' }))
vi.mock('../../hooks/routing/useNavigate', () => ({ useNavigate: () => vi.fn() }))

const mockDeleteSystemAssignment = vi.fn()
const mockDeleteProjectAssignment = vi.fn()

const mockMutationReturn = (mutateFn: ReturnType<typeof vi.fn>) =>
  ({
    mutate: mutateFn,
    mutateAsync: vi.fn(),
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
  }) as never

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

// ── Test Data ────────────────────────────────────────────────────────────────

type AssignmentResource = {
  id: string
  principal_type: 'user' | 'group' | 'service_account'
  principal_id: string
  principal_name: string
  role_name: string
  role_description: string | null
  role_policies: string[]
  project_id: string | null
  project_name: string | null
  created_at: string | null
}

const mockUserAssignments: AssignmentResource[] = [
  {
    id: 'ua1',
    principal_type: 'user',
    principal_id: 'u1',
    principal_name: 'user-one',
    role_name: 'admin-role',
    role_description: 'Full access',
    role_policies: ['policy-a', 'policy-b'],
    project_id: null,
    project_name: null,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'ua2',
    principal_type: 'user',
    principal_id: 'u1',
    principal_name: 'user-one',
    role_name: 'viewer-role',
    role_description: 'Read-only',
    role_policies: ['policy-c'],
    project_id: null,
    project_name: null,
    created_at: '2024-01-02T00:00:00Z',
  },
]

const mockGroupAssignments: AssignmentResource[] = [
  {
    id: 'ga1',
    principal_type: 'group',
    principal_id: 'g1',
    principal_name: 'group-one',
    role_name: 'admin-role',
    role_description: 'Full access',
    role_policies: ['policy-a', 'policy-b'],
    project_id: null,
    project_name: null,
    created_at: '2024-01-01T00:00:00Z',
  },
]

const mockSaAssignments: AssignmentResource[] = [
  {
    id: 'sa-a1',
    principal_type: 'service_account',
    principal_id: 'sa-1',
    principal_name: 'my-service-account',
    role_name: 'project-editor',
    role_description: 'Edit project resources',
    role_policies: ['project.edit'],
    project_id: 'proj1',
    project_name: 'Project Alpha',
    created_at: '2024-03-01T00:00:00Z',
  },
]

// ── Helpers ──────────────────────────────────────────────────────────────────

function setupMocks(overrides?: {
  userAssignments?: AssignmentResource[]
  groupAssignments?: AssignmentResource[]
  serviceAccountAssignments?: AssignmentResource[]
}) {
  const mockRefetch = vi.fn().mockResolvedValue({})

  vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/users/{user_id}/role_assignments') {
      const resources = overrides?.userAssignments ?? mockUserAssignments
      return {
        data: { resources, next: null },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never
    }
    if (path === '/groups/{group_id}/role_assignments') {
      const resources = overrides?.groupAssignments ?? mockGroupAssignments
      return {
        data: { resources, next: null },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never
    }
    if (path === '/role_assignments') {
      const resources = overrides?.serviceAccountAssignments ?? mockSaAssignments
      return {
        data: { resources, next: null },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never
    }
    if (path === '/projects') {
      return { data: [], isPending: false, isError: false, error: null, refetch: vi.fn() } as never
    }
    return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
  })

  vi.mocked(accessClient.useMutation).mockImplementation((_method: string, path: string) => {
    if (path === '/role_assignments/{assignment_id}') {
      return mockMutationReturn(mockDeleteSystemAssignment)
    }
    if (path === '/projects/{project_id}/role_assignments/{assignment_id}') {
      return mockMutationReturn(mockDeleteProjectAssignment)
    }
    return mockMutationReturn(vi.fn())
  })

  return { mockRefetch }
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('RoleAssignmentsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    searchParamsMock.reset()
    vi.mocked(useAllRoles).mockReturnValue({ roles: [], isLoading: false, error: null, refetch: vi.fn() })
    const emptyProjectsMock = { projects: [], isLoading: false, error: null, refetch: vi.fn() }
    vi.mocked(useAllProjects).mockReturnValue(emptyProjectsMock)
    vi.mocked(useSelectableProjects).mockReturnValue(emptyProjectsMock)
    setupMocks()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with data', async () => {
      const { container } = render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      setupMocks({ userAssignments: [] })
      const { container } = render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with expanded rows', async () => {
      const user = userEvent.setup()

      const { container } = render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /expand all/i }))
      await waitFor(() => {
        expect(screen.getByText('policy-a')).toBeVisible()
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Loading and error states', () => {
    it('renders loading state when query is pending', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/users/{user_id}/role_assignments') {
          return { data: undefined, isPending: true, isError: false, error: null, refetch: vi.fn() } as never
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
      })
      vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn(vi.fn()))

      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })

    it('renders error state when query fails', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/users/{user_id}/role_assignments') {
          return {
            data: undefined,
            isPending: false,
            isError: true,
            error: new Error('Server error'),
            refetch: vi.fn(),
          } as never
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
      })
      vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn(vi.fn()))

      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByText('Error loading role assignments')).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('shows empty state when user has no assignments', () => {
      setupMocks({ userAssignments: [] })
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.getByText('No role assignments yet')).toBeInTheDocument()
      expect(screen.getByText('No roles have been assigned to this user.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Assign role' })).toBeInTheDocument()
    })

    it('shows empty state when group has no assignments', () => {
      setupMocks({ groupAssignments: [] })
      render(<RoleAssignmentsPanel principalType="group" principalId="g1" />, { wrapper })

      expect(screen.getByText('No role assignments yet')).toBeInTheDocument()
      expect(screen.getByText('No roles have been assigned to this group.')).toBeInTheDocument()
    })

    it('opens assign role modal from empty state', async () => {
      const user = userEvent.setup()
      setupMocks({ userAssignments: [] })
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Assign role' }))

      await waitFor(() => {
        expect(screen.getByText('Assign roles')).toBeInTheDocument()
      })
    })

    it('closes assign role modal from empty state via Cancel', async () => {
      const user = userEvent.setup()
      setupMocks({ userAssignments: [] })
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Assign role' }))

      await waitFor(() => {
        expect(screen.getByText('Assign roles')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Assign roles')).not.toBeInTheDocument()
      })
    })
  })

  describe('Table rendering (user)', () => {
    it('renders table with correct columns', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      expect(table).toBeInTheDocument()

      expect(screen.getByRole('columnheader', { name: 'Role name' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Scope' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Project' })).toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: 'Policies' })).not.toBeInTheDocument()
    })

    it('renders all assignment rows', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      const rows = within(table).getAllByRole('row')

      // Header row + 2 data rows
      expect(rows).toHaveLength(3)

      expect(screen.getByText('admin-role')).toBeInTheDocument()
      expect(screen.getByText('viewer-role')).toBeInTheDocument()
    })

    it('shows role description', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByText('Full access')).toBeInTheDocument()
      expect(screen.getByText('Read-only')).toBeInTheDocument()
    })

    it('shows scope as System labels', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const systemLabels = screen.getAllByText('System')
      expect(systemLabels.length).toBeGreaterThanOrEqual(2)
    })

    it('shows policies as labels when row is expanded', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.queryByText('policy-a')).not.toBeVisible()

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('policy-a')).toBeVisible()
      expect(screen.getByText('policy-b')).toBeVisible()

      await user.click(expandButtons[1])

      expect(screen.getByText('policy-c')).toBeVisible()
    })

    it('shows "Assign role" button', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByRole('button', { name: 'Assign role' })).toBeInTheDocument()
    })
  })

  describe('Expandable rows', () => {
    it('expand-all button expands all rows on the current page', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.queryByText('policy-a')).not.toBeVisible()

      await user.click(screen.getByRole('button', { name: /expand all/i }))

      expect(screen.getByText('policy-a')).toBeVisible()
      expect(screen.getByText('policy-c')).toBeVisible()
    })
  })

  describe('Table rendering (group)', () => {
    it('renders group assignments', () => {
      render(<RoleAssignmentsPanel principalType="group" principalId="g1" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      const rows = within(table).getAllByRole('row')

      // Header + 1 data row
      expect(rows).toHaveLength(2)
      expect(screen.getByText('admin-role')).toBeInTheDocument()
    })
  })

  describe('Role without description or policies', () => {
    it('shows dash for missing description', () => {
      setupMocks({
        userAssignments: [
          {
            id: 'ua1',
            principal_type: 'user',
            principal_id: 'u1',
            principal_name: 'user-one',
            role_name: 'no-desc-role',
            role_description: null,
            role_policies: [],
            project_id: null,
            project_name: null,
            created_at: null,
          },
        ],
      })

      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const dashes = screen.getAllByText('-')
      expect(dashes.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Filtering', () => {
    it('renders the filter bar', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByPlaceholderText('Filter by role name')).toBeInTheDocument()
    })

    it('filters rows by name', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const filterInput = screen.getByPlaceholderText('Filter by role name')
      await user.type(filterInput, 'admin')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('admin-role')).toBeInTheDocument()
        expect(screen.queryByText('viewer-role')).not.toBeInTheDocument()
      })
    })

    it('shows filter empty state when no rows match filter', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const filterInput = screen.getByPlaceholderText('Filter by role name')
      await user.type(filterInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })

    it('clears filters from the filter empty state', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const filterInput = screen.getByPlaceholderText('Filter by role name')
      await user.type(filterInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })

      const clearButtons = screen.getAllByRole('button', { name: /Clear all filters/i })
      await user.click(clearButtons[clearButtons.length - 1])

      await waitFor(() => {
        expect(screen.getByText('admin-role')).toBeInTheDocument()
        expect(screen.getByText('viewer-role')).toBeInTheDocument()
      })
    })

    it('clears filters from the FilterBar clear-all button', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const filterInput = screen.getByPlaceholderText('Filter by role name')
      await user.type(filterInput, 'admin')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('admin-role')).toBeInTheDocument()
        expect(screen.queryByText('viewer-role')).not.toBeInTheDocument()
      })

      const clearButtons = screen.getAllByRole('button', { name: /Clear all filters/i })
      await user.click(clearButtons[0])

      await waitFor(() => {
        expect(screen.getByText('admin-role')).toBeInTheDocument()
        expect(screen.getByText('viewer-role')).toBeInTheDocument()
      })
    })
  })

  describe('Pagination', () => {
    it('renders pagination footer', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })
      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
    })

    it('paginates rows and supports next/prev navigation', async () => {
      const manyAssignments: AssignmentResource[] = Array.from({ length: 25 }, (_, i) => ({
        id: `ua-${String(i)}`,
        principal_type: 'user' as const,
        principal_id: 'u1',
        principal_name: 'user-one',
        role_name: `role-${String(i)}`,
        role_description: null,
        role_policies: [],
        project_id: null,
        project_name: null,
        created_at: '2024-01-01T00:00:00Z',
      }))

      setupMocks({ userAssignments: manyAssignments })

      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.getByText('role-0')).toBeInTheDocument()
      expect(screen.getByText('role-19')).toBeInTheDocument()
      expect(screen.queryByText('role-20')).not.toBeInTheDocument()

      const nextButton = screen.getByRole('button', { name: /go to next page/i })
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.getByText('role-20')).toBeInTheDocument()
      })
      expect(screen.queryByText('role-0')).not.toBeInTheDocument()

      const prevButton = screen.getByRole('button', { name: /go to previous page/i })
      await user.click(prevButton)

      await waitFor(() => {
        expect(screen.getByText('role-0')).toBeInTheDocument()
      })
    })

    it('resets to the first page when per-page size changes', async () => {
      const manyAssignments: AssignmentResource[] = Array.from({ length: 25 }, (_, i) => ({
        id: `ua-${String(i)}`,
        principal_type: 'user' as const,
        principal_id: 'u1',
        principal_name: 'user-one',
        role_name: `role-${String(i)}`,
        role_description: null,
        role_policies: [],
        project_id: null,
        project_name: null,
        created_at: '2024-01-01T00:00:00Z',
      }))

      setupMocks({ userAssignments: manyAssignments })

      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /go to next page/i }))
      await waitFor(() => {
        expect(screen.getByText('role-20')).toBeInTheDocument()
      })

      const perPageToggle = screen.getByRole('button', { name: /21 - 25 of 25/i })
      await user.click(perPageToggle)
      const option10 = await screen.findByRole('menuitem', { name: /10 per page/i })
      await user.click(option10)

      await waitFor(() => {
        expect(screen.getByText('role-0')).toBeInTheDocument()
        expect(screen.queryByText('role-20')).not.toBeInTheDocument()
      })
    })
  })

  describe('Assign role modal', () => {
    it('opens assign role modal when "Assign role" button is clicked', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Assign role' }))

      await waitFor(() => {
        expect(screen.getByText('Assign roles')).toBeInTheDocument()
      })
    })

    it('closes assign role modal when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Assign role' }))

      await waitFor(() => {
        expect(screen.getByText('Assign roles')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Assign roles')).not.toBeInTheDocument()
      })
    })
  })

  describe('Unassign role', () => {
    it('opens unassign dialog when Unassign action is clicked', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
        expect(screen.getByText(/This unassigns the role/)).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Unassign' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      })
    })

    it('closes unassign dialog when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Unassign role?')).not.toBeInTheDocument()
      })
    })

    it('calls deleteSystemAssignment when confirming unassign for system-scoped role', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteSystemAssignment).toHaveBeenCalledWith(
          { params: { path: { assignment_id: 'ua1' } } },
          expect.objectContaining({
            onSuccess: expect.any(Function) as unknown,
            onError: expect.any(Function) as unknown,
            onSettled: expect.any(Function) as unknown,
          })
        )
      })
    })

    it('calls deleteProjectAssignment for project-scoped roles', async () => {
      setupMocks({
        userAssignments: [
          {
            id: 'pa1',
            principal_type: 'user',
            principal_id: 'u1',
            principal_name: 'user-one',
            role_name: 'admin-role',
            role_description: 'Full access',
            role_policies: ['policy-a'],
            project_id: 'proj1',
            project_name: 'Project Alpha',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      })

      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteProjectAssignment).toHaveBeenCalledWith(
          { params: { path: { project_id: 'proj1', assignment_id: 'pa1' } } },
          expect.objectContaining({
            onSuccess: expect.any(Function) as unknown,
            onError: expect.any(Function) as unknown,
            onSettled: expect.any(Function) as unknown,
          })
        )
      })
    })

    it('shows success alert after successful unassign', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteSystemAssignment).toHaveBeenCalled()
      })

      const callbacks = mockDeleteSystemAssignment.mock.calls[0][1] as {
        onSuccess: () => void
        onSettled: () => void
      }

      await waitFor(() => {
        callbacks.onSuccess()
      })

      expect(screen.getByText('Role unassigned')).toBeInTheDocument()
    })

    it('refetches assignments and invalidates permission caches after successful unassign (AAP-81033)', async () => {
      // Arrange — revoke path must refresh assignment list and useCanI / what_can_i caches
      const { mockRefetch } = setupMocks()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined)
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteSystemAssignment).toHaveBeenCalled()
      })

      const callbacks = mockDeleteSystemAssignment.mock.calls[0][1] as {
        onSuccess: () => void
      }

      // Act
      await waitFor(() => {
        callbacks.onSuccess()
      })

      // Assert — refetchAndInvalidateAuthz: refetch list + invalidate can_i / all-permissions
      expect(mockRefetch).toHaveBeenCalled()
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['authz', 'can_i'] })
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['all-permissions'] })
      expect(screen.getByText('Role unassigned')).toBeInTheDocument()

      invalidateSpy.mockRestore()
    })

    it('shows error alert after failed unassign', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteSystemAssignment).toHaveBeenCalled()
      })

      const callbacks = mockDeleteSystemAssignment.mock.calls[0][1] as {
        onError: (err: unknown) => void
        onSettled: () => void
      }

      await waitFor(() => {
        callbacks.onError(new Error('Server error'))
      })

      expect(screen.getByText('Failed to unassign role')).toBeInTheDocument()
    })
  })

  describe('Service account principal', () => {
    it('renders SA assignments in table', () => {
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      const rows = within(table).getAllByRole('row')

      // Header + 1 data row
      expect(rows).toHaveLength(2)
      expect(screen.getByText('project-editor')).toBeInTheDocument()
      expect(screen.getByText('Edit project resources')).toBeInTheDocument()
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    it('links project-scoped assignment project names to project detail', () => {
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" />, { wrapper })

      expect(screen.getByRole('link', { name: 'Project Alpha' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/projects/proj1'
      )
    })

    it('keeps system-scoped assignment project column as plain text', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.queryByRole('link', { name: 'System' })).not.toBeInTheDocument()
      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[1]).getByText('-')).toBeInTheDocument()
    })

    it('shows empty state for SA with no assignments', () => {
      setupMocks({ serviceAccountAssignments: [] })
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" />, { wrapper })

      expect(screen.getByText('No role assignments yet')).toBeInTheDocument()
      expect(screen.getByText('No roles have been assigned to this service account.')).toBeInTheDocument()
    })

    it('opens assign role modal from SA panel', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Assign role' }))

      await waitFor(() => {
        expect(screen.getByText('Assign roles')).toBeInTheDocument()
      })
    })

    it('calls deleteProjectAssignment when unassigning SA project-scoped role', async () => {
      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" />, { wrapper })

      const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabButtons[0])

      const unassignItem = await screen.findByRole('menuitem', { name: /Unassign/i })
      await user.click(unassignItem)

      await waitFor(() => {
        expect(screen.getByText('Unassign role?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Unassign' }))

      await waitFor(() => {
        expect(mockDeleteProjectAssignment).toHaveBeenCalledWith(
          { params: { path: { project_id: 'proj1', assignment_id: 'sa-a1' } } },
          expect.objectContaining({
            onSuccess: expect.any(Function) as unknown,
            onError: expect.any(Function) as unknown,
            onSettled: expect.any(Function) as unknown,
          })
        )
      })
    })
  })

  describe('Hidden columns', () => {
    it('hides the Scope column header and cells when scope is hidden', () => {
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" hiddenColumns={['scope']} />, {
        wrapper,
      })

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      expect(within(table).queryByRole('columnheader', { name: 'Scope' })).not.toBeInTheDocument()
      expect(within(table).getByRole('columnheader', { name: 'Role name' })).toBeInTheDocument()
      expect(within(table).getByRole('columnheader', { name: 'Description' })).toBeInTheDocument()
      expect(within(table).getByRole('columnheader', { name: 'Project' })).toBeInTheDocument()
      expect(within(table).queryByRole('columnheader', { name: 'Policies' })).not.toBeInTheDocument()
    })

    it('does not offer Scope as a filter category when scope column is hidden', () => {
      render(<RoleAssignmentsPanel principalType="user" principalId="u1" hiddenColumns={['scope']} />, { wrapper })

      expect(screen.queryByPlaceholderText('Filter by scope')).not.toBeInTheDocument()
      expect(screen.getByPlaceholderText('Filter by role name')).toBeInTheDocument()
    })

    it('sorts correctly with hidden scope column', async () => {
      setupMocks({
        serviceAccountAssignments: [
          {
            id: 'sa-a1',
            principal_type: 'service_account',
            principal_id: 'sa-1',
            principal_name: 'my-service-account',
            role_name: 'beta-role',
            role_description: 'B role',
            role_policies: [],
            project_id: 'proj1',
            project_name: 'Project Alpha',
            created_at: '2024-03-01T00:00:00Z',
          },
          {
            id: 'sa-a2',
            principal_type: 'service_account',
            principal_id: 'sa-1',
            principal_name: 'my-service-account',
            role_name: 'alpha-role',
            role_description: 'A role',
            role_policies: [],
            project_id: 'proj2',
            project_name: 'Project Beta',
            created_at: '2024-03-02T00:00:00Z',
          },
        ],
      })

      const user = userEvent.setup()
      render(<RoleAssignmentsPanel principalType="service_account" principalId="sa-1" hiddenColumns={['scope']} />, {
        wrapper,
      })

      const roleNameHeader = screen.getByRole('columnheader', { name: 'Role name' })
      const sortButton = within(roleNameHeader).getByRole('button')
      await user.click(sortButton)

      const table = screen.getByRole('grid', { name: 'Role assignments table' })
      const rows = within(table).getAllByRole('row')
      const dataRows = rows.slice(1)

      const firstRowCells = within(dataRows[0]).getAllByRole('cell')
      expect(firstRowCells[1]).toHaveTextContent('alpha-role')
    })

    it('has no accessibility violations with hidden columns', async () => {
      const { container } = render(
        <RoleAssignmentsPanel principalType="service_account" principalId="sa-1" hiddenColumns={['scope']} />,
        { wrapper }
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('403 forbidden state', () => {
    it('shows info alert when query returns 403', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/users/{user_id}/role_assignments') {
          return {
            data: undefined,
            isPending: false,
            isError: true,
            error: { status: 403, code: 'AUTHORIZATION_DENIED' },
            refetch: vi.fn(),
          } as never
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
      })
      vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn(vi.fn()))

      render(<RoleAssignmentsPanel principalType="user" principalId="u1" />, { wrapper })

      expect(screen.getByText('Showing project-scoped roles only')).toBeInTheDocument()
    })
  })
})
