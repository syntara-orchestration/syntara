import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { routerTestState, MockLink } from '../../../test/setup'
import { accessClient, accessFetchClient } from '../../access/accessClient'
import { useGroupPermissions } from '../useGroupPermissions'

import { GroupDetail } from './GroupDetail'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../useGroupPermissions')

const VALID_GROUP_ID = 'g-1234-5678-abcd'

let mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}`
const mockUseParams = vi.fn(() => ({ groupId: VALID_GROUP_ID }))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => mockUseParams(),
    useNavigate: () => routerTestState.navigate,
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: mockLocationValue, searchStr: '' } }
      return opts?.select ? opts.select(state) : state
    },
  }
})

vi.mock('../../../hooks/routing/useSearchParams', async () => {
  const React = await import('react')
  return {
    useSearchParams: () => React.useState(new URLSearchParams()),
  }
})

vi.mock('./GroupMembersPanel', () => ({
  GroupMembersPanel: ({ groupId, onMembershipChange }: { groupId: string; onMembershipChange: () => void }) => (
    <div data-testid="group-members-panel">
      Members panel for {groupId}
      <button type="button" onClick={onMembershipChange}>
        Trigger membership change
      </button>
    </div>
  ),
}))

vi.mock('../RoleAssignmentsPanel', () => ({
  RoleAssignmentsPanel: ({ principalOrGroup, principalId }: { principalOrGroup: string; principalId: string }) => (
    <div data-testid="role-assignments-panel">
      Roles for {principalOrGroup}:{principalId}
    </div>
  ),
}))

vi.mock('../GroupFormModal', () => ({
  GroupFormModal: ({ isOpen, onClose, onSuccess }: { isOpen: boolean; onClose: () => void; onSuccess: () => void }) =>
    isOpen ? (
      <div data-testid="group-form-modal">
        <button type="button" onClick={onClose}>
          Close modal
        </button>
        <button type="button" onClick={onSuccess}>
          Save modal
        </button>
      </div>
    ) : null,
}))

vi.mock('./GroupNotFoundState', () => ({
  GroupNotFoundState: ({ onBack, onRetry }: { onBack: () => void; onRetry: () => void }) => (
    <div>
      <span>Group not found</span>
      <button type="button" onClick={onBack}>
        Back to groups
      </button>
      <button type="button" onClick={onRetry}>
        Retry
      </button>
    </div>
  ),
}))

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockGroup = {
  id: VALID_GROUP_ID,
  name: 'developers',
  description: 'Developer group',
  is_builtin: false,
  created_at: '2024-01-15T00:00:00Z',
  updated_at: '2024-06-10T12:00:00Z',
}

const mockAuthenticatedGroup = {
  id: 'auth-group-id',
  name: 'authenticated',
  description: 'All authenticated users',
  is_builtin: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const mockMembersData = {
  resources: [
    { id: 'u1', username: 'alice' },
    { id: 'u2', username: 'bob' },
  ],
  total: 2,
}

const mockRoleAssignmentsData = {
  resources: [
    { id: 'ra1', role: 'admin', scope: 'global' },
    { id: 'ra2', role: 'viewer', scope: 'global' },
    { id: 'ra3', role: 'editor', scope: 'project-1' },
  ],
  total: 3,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

/** Build a mock return value for accessClient.useQuery */
function buildQueryResult(overrides: {
  data?: unknown
  isPending?: boolean
  isError?: boolean
  error?: Error | null
  refetch?: ReturnType<typeof vi.fn>
}) {
  return {
    data: overrides.data,
    isPending: overrides.isPending ?? false,
    isError: overrides.isError ?? false,
    error: overrides.error ?? null,
    refetch: overrides.refetch ?? vi.fn().mockResolvedValue({}),
  } as never
}

/**
 * Configure accessClient.useQuery to return per-path results.
 * Each entry in `pathResults` maps a path suffix to a query result override.
 * Paths not listed fall back to an empty success response.
 */
function mockQueryByPath(pathResults: Record<string, Parameters<typeof buildQueryResult>[0]>) {
  vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
    const key = Object.keys(pathResults).find((k) => path === k)
    return buildQueryResult(key ? pathResults[key] : {})
  })
}

function mockSuccessQueries(group = mockGroup, members = mockMembersData, roleAssignments = mockRoleAssignmentsData) {
  mockQueryByPath({
    '/groups/{group_id}': { data: group },
    '/groups/{group_id}/members': { data: members },
    '/groups/{group_id}/role_assignments': { data: roleAssignments },
  })

  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GroupDetail', () => {
  beforeEach(() => {
    queryClient.clear()
    routerTestState.navigate.mockClear()
    mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}`
    mockUseParams.mockReturnValue({ groupId: VALID_GROUP_ID })
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)
    vi.mocked(useGroupPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canManageMembers: true,
      isLoading: false,
      tooltips: { create: '', update: '', delete: '', manageMembers: '' },
    })
    mockSuccessQueries()
  })

  // ---- Rendering ----------------------------------------------------------

  describe('Rendering', () => {
    it('renders group name as heading', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('heading', { name: 'developers' })).toBeInTheDocument()
    })

    it('renders description list fields on the Details tab', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.getByText('Name')).toBeInTheDocument()
      const breadcrumbNav = screen.getByRole('navigation', { name: 'Breadcrumb' })
      expect(within(breadcrumbNav).getByText('developers')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'developers' })).toBeInTheDocument()
      expect(screen.getByText('Description')).toBeInTheDocument()
      expect(screen.getByText('Developer group')).toBeInTheDocument()
      expect(screen.getByText('Created')).toBeInTheDocument()
      expect(screen.getByText(/Jan.*2024/i)).toBeInTheDocument()
      expect(screen.getByText('Updated')).toBeInTheDocument()
      expect(screen.getByText(/Jun.*10.*2024/i)).toBeInTheDocument()
    })

    it('shows dash when description is null', () => {
      mockSuccessQueries({ ...mockGroup, description: null } as unknown as typeof mockGroup)
      render(<GroupDetail />, { wrapper })

      expect(screen.getByText('-')).toBeInTheDocument()
    })

    it('shows Built-in label for built-in groups', () => {
      mockSuccessQueries({ ...mockGroup, is_builtin: true })
      render(<GroupDetail />, { wrapper })

      expect(screen.getByText('Built-in')).toBeInTheDocument()
    })

    it('does not show Built-in label for non-built-in groups', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.queryByText('Built-in')).not.toBeInTheDocument()
    })

    it('renders null when groupData is undefined and no error/loading', () => {
      mockQueryByPath({
        '/groups/{group_id}': { data: undefined },
        '/groups/{group_id}/members': { data: mockMembersData },
      })

      const { container } = render(<GroupDetail />, { wrapper })

      expect(container.innerHTML).toBe('')
    })
  })

  // ---- Edit button --------------------------------------------------------

  describe('Edit button', () => {
    it('renders Edit group button for non-built-in groups', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('button', { name: 'Edit group' })).toBeInTheDocument()
    })

    it('does not render Edit group button for built-in groups', () => {
      mockSuccessQueries({ ...mockGroup, is_builtin: true })
      render(<GroupDetail />, { wrapper })

      expect(screen.queryByRole('button', { name: 'Edit group' })).not.toBeInTheDocument()
    })

    it('opens the edit modal when Edit group is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Edit group' }))

      expect(screen.getByTestId('group-form-modal')).toBeInTheDocument()
    })

    it('disables Edit group button when canUpdate is false', () => {
      vi.mocked(useGroupPermissions).mockReturnValue({
        canCreate: true,
        canUpdate: false,
        canDelete: true,
        canManageMembers: true,
        isLoading: false,
        tooltips: { create: '', update: 'Insufficient permissions', delete: '', manageMembers: '' },
      })

      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('button', { name: 'Edit group' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('renders kebab menu with delete action for non-built-in groups', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('button', { name: 'Group actions' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Group actions' }))

      expect(screen.getByRole('menuitem', { name: /delete group/i })).toBeInTheDocument()
    })

    it('opens delete confirmation dialog from kebab menu', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Group actions' }))
      await user.click(screen.getByRole('menuitem', { name: /delete group/i }))

      expect(screen.getByText('Delete group?')).toBeInTheDocument()
    })

    it('closes delete confirmation dialog when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Group actions' }))
      await user.click(screen.getByRole('menuitem', { name: /delete group/i }))
      expect(screen.getByText('Delete group?')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(screen.queryByText('Delete group?')).not.toBeInTheDocument()
    })

    it('disables delete action in kebab menu when canDelete is false', async () => {
      vi.mocked(useGroupPermissions).mockReturnValue({
        canCreate: true,
        canUpdate: true,
        canDelete: false,
        canManageMembers: true,
        isLoading: false,
        tooltips: { create: '', update: '', delete: 'Insufficient permissions', manageMembers: '' },
      })

      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Group actions' }))
      expect(screen.getByRole('menuitem', { name: /delete group/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('closes the edit modal when Close modal is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Edit group' }))
      expect(screen.getByTestId('group-form-modal')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Close modal' }))
      expect(screen.queryByTestId('group-form-modal')).not.toBeInTheDocument()
    })

    it('calls refetch after modal onSuccess', async () => {
      const mockRefetch = vi.fn().mockResolvedValue({})
      mockQueryByPath({
        '/groups/{group_id}': { data: mockGroup, refetch: mockRefetch },
        '/groups/{group_id}/members': { data: mockMembersData },
      })

      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Edit group' }))
      await user.click(screen.getByRole('button', { name: 'Save modal' }))

      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  // ---- Loading state ------------------------------------------------------

  describe('Loading state', () => {
    it('shows loading spinner when group query is pending', () => {
      mockQueryByPath({
        '/groups/{group_id}': { isPending: true },
        '/groups/{group_id}/members': { data: mockMembersData },
      })

      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })
  })

  // ---- Error state --------------------------------------------------------

  describe('Error state', () => {
    it('shows GroupNotFoundState when query has an error', () => {
      mockQueryByPath({
        '/groups/{group_id}': { isError: true, error: new Error('Not found') },
      })

      render(<GroupDetail />, { wrapper })

      expect(screen.getByText('Group not found')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Back to groups' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    })

    it('navigates back to groups list when Back to groups is clicked', async () => {
      const user = userEvent.setup()
      mockQueryByPath({
        '/groups/{group_id}': { isError: true, error: new Error('Not found') },
      })

      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Back to groups' }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/system-administration/access-management/groups' })
    })

    it('calls refetch when Retry is clicked in error state', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn().mockResolvedValue({})
      mockQueryByPath({
        '/groups/{group_id}': { isError: true, error: new Error('Not found'), refetch: mockRefetch },
      })

      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Retry' }))

      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  // ---- Tabs ---------------------------------------------------------------

  describe('Tabs', () => {
    it('renders Details, Members, and Assignments tabs for regular groups', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('tab', { name: /Details/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Members/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Assignments/i })).toBeInTheDocument()
    })

    it('shows Details tab content by default', () => {
      render(<GroupDetail />, { wrapper })

      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Developer group')).toBeInTheDocument()
      expect(screen.getByText('Created')).toBeInTheDocument()
    })

    it('hides Members tab for authenticated group', () => {
      mockSuccessQueries(mockAuthenticatedGroup)
      render(<GroupDetail />, { wrapper })

      expect(screen.getByRole('tab', { name: /Details/i })).toBeInTheDocument()
      expect(screen.queryByRole('tab', { name: /Members/i })).not.toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Assignments/i })).toBeInTheDocument()
    })

    it('displays member count badge on Members tab', () => {
      render(<GroupDetail />, { wrapper })

      const membersTab = screen.getByRole('tab', { name: /Members/i })
      expect(membersTab).toHaveTextContent('2')
    })

    it('uses resources.length for member count when total is missing', () => {
      mockSuccessQueries(mockGroup, {
        resources: [{ id: 'u1', username: 'alice' }],
      } as typeof mockMembersData)

      render(<GroupDetail />, { wrapper })

      const membersTab = screen.getByRole('tab', { name: /Members/i })
      expect(membersTab).toHaveTextContent('1')
    })

    it('displays role assignment count badge on Assignments tab', () => {
      render(<GroupDetail />, { wrapper })

      const rolesTab = screen.getByRole('tab', { name: /Assignments/i })
      expect(rolesTab).toHaveTextContent('3')
    })

    it('uses total for role assignment count when both total and resources are present', () => {
      mockSuccessQueries(mockGroup, mockMembersData, {
        resources: [{ id: 'ra1', role: 'admin', scope: 'global' }],
        total: 10,
      })
      render(<GroupDetail />, { wrapper })

      const rolesTab = screen.getByRole('tab', { name: /Assignments/i })
      expect(rolesTab).toHaveTextContent('10')
    })

    it('falls back to resources.length for role assignment count when total is undefined', () => {
      mockSuccessQueries(mockGroup, mockMembersData, {
        resources: [
          { id: 'ra1', role: 'admin', scope: 'global' },
          { id: 'ra2', role: 'viewer', scope: 'global' },
        ],
      } as typeof mockRoleAssignmentsData)
      render(<GroupDetail />, { wrapper })

      const rolesTab = screen.getByRole('tab', { name: /Assignments/i })
      expect(rolesTab).toHaveTextContent('2')
    })

    it('shows zero role assignment count when no data is available', () => {
      mockQueryByPath({
        '/groups/{group_id}': { data: mockGroup },
        '/groups/{group_id}/members': { data: mockMembersData },
        '/groups/{group_id}/role_assignments': { data: undefined },
      })

      render(<GroupDetail />, { wrapper })

      const rolesTab = screen.getByRole('tab', { name: /Assignments/i })
      expect(rolesTab).toHaveTextContent('0')
    })

    it('shows zero member count when no members data is available', () => {
      mockQueryByPath({
        '/groups/{group_id}': { data: mockGroup },
        '/groups/{group_id}/members': { data: undefined },
      })

      render(<GroupDetail />, { wrapper })

      const membersTab = screen.getByRole('tab', { name: /Members/i })
      expect(membersTab).toHaveTextContent('0')
    })

    it('navigates to members URL when Members tab is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('tab', { name: /Members/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: `/system-administration/access-management/groups/${VALID_GROUP_ID}/members`,
      })
    })

    it('navigates to roles URL when Assignments tab is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupDetail />, { wrapper })

      await user.click(screen.getByRole('tab', { name: /Assignments/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: `/system-administration/access-management/groups/${VALID_GROUP_ID}/roles`,
      })
    })

    it('renders Members panel when URL is /members', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/members`
      render(<GroupDetail />, { wrapper })

      expect(screen.getByTestId('group-members-panel')).toBeInTheDocument()
      // Details content should not be visible
      expect(screen.queryByText('Description')).not.toBeInTheDocument()
    })

    it('renders Roles panel when URL is /roles', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/roles`
      render(<GroupDetail />, { wrapper })

      expect(screen.getByTestId('role-assignments-panel')).toBeInTheDocument()
      expect(screen.queryByText('Description')).not.toBeInTheDocument()
    })

    it('does not render Members panel for authenticated group even on /members URL', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/members`
      mockSuccessQueries(mockAuthenticatedGroup)
      render(<GroupDetail />, { wrapper })

      expect(screen.queryByTestId('group-members-panel')).not.toBeInTheDocument()
    })
  })

  // ---- Members query behavior ---------------------------------------------

  describe('Members query', () => {
    it('disables members query for authenticated group', () => {
      mockSuccessQueries(mockAuthenticatedGroup)
      render(<GroupDetail />, { wrapper })

      // The useQuery mock is called multiple times (React may re-render).
      // Find the last call for members path to get the final enabled value.
      const calls = vi.mocked(accessClient.useQuery).mock.calls
      const membersCalls = calls.filter((call) => call[1] === '/groups/{group_id}/members')
      expect(membersCalls.length).toBeGreaterThan(0)
      const lastMembersCall = membersCalls.at(-1)
      expect(lastMembersCall?.[3]).toEqual(expect.objectContaining({ enabled: false }))
    })

    it('enables members query for regular groups', () => {
      render(<GroupDetail />, { wrapper })

      const calls = vi.mocked(accessClient.useQuery).mock.calls
      const membersCalls = calls.filter((call) => call[1] === '/groups/{group_id}/members')
      expect(membersCalls.length).toBeGreaterThan(0)
      const lastMembersCall = membersCalls.at(-1)
      expect(lastMembersCall?.[3]).toEqual(expect.objectContaining({ enabled: true }))
    })
  })

  // ---- Edge cases for groupId and memberCount ----------------------------

  describe('Edge cases', () => {
    it('handles undefined groupId gracefully', () => {
      mockUseParams.mockReturnValue({ groupId: undefined } as never)
      mockQueryByPath({})

      const { container } = render(<GroupDetail />, { wrapper })

      // With undefined groupId, enabled is false, so no data, returns null
      expect(container.innerHTML).toBe('')
    })

    it('renders roles tab for authenticated group', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/roles`
      mockSuccessQueries(mockAuthenticatedGroup)
      render(<GroupDetail />, { wrapper })

      // Roles tab should render for authenticated group (no members tab though)
      expect(screen.getByTestId('role-assignments-panel')).toBeInTheDocument()
    })

    it('renders no tab content for unrecognized tab slug', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/unknown`
      render(<GroupDetail />, { wrapper })

      // Neither details, members, nor roles content should show
      expect(screen.queryByText('Name')).not.toBeInTheDocument()
      expect(screen.queryByTestId('group-members-panel')).not.toBeInTheDocument()
      expect(screen.queryByTestId('role-assignments-panel')).not.toBeInTheDocument()
    })

    it('does not show members panel on members URL for authenticated group', () => {
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/members`
      mockSuccessQueries(mockAuthenticatedGroup)
      render(<GroupDetail />, { wrapper })

      // The members panel should not render for authenticated group
      expect(screen.queryByTestId('group-members-panel')).not.toBeInTheDocument()
    })

    it('uses total for memberCount when both total and resources are present', () => {
      mockSuccessQueries(mockGroup, { resources: [{ id: 'u1', username: 'alice' }], total: 5 })
      render(<GroupDetail />, { wrapper })

      const membersTab = screen.getByRole('tab', { name: /Members/i })
      expect(membersTab).toHaveTextContent('5')
    })

    it('falls back to resources.length when total is undefined', () => {
      mockSuccessQueries(mockGroup, {
        resources: [
          { id: 'u1', username: 'a' },
          { id: 'u2', username: 'b' },
          { id: 'u3', username: 'c' },
        ],
      } as typeof mockMembersData)
      render(<GroupDetail />, { wrapper })

      const membersTab = screen.getByRole('tab', { name: /Members/i })
      expect(membersTab).toHaveTextContent('3')
    })
  })

  // ---- onMembersChange callback -------------------------------------------

  describe('onMembersChange callback', () => {
    it('calls membersQuery.refetch when onMembersChange fires', async () => {
      const user = userEvent.setup()
      const mockMembersRefetch = vi.fn().mockResolvedValue({})
      mockQueryByPath({
        '/groups/{group_id}': { data: mockGroup },
        '/groups/{group_id}/members': { data: mockMembersData, refetch: mockMembersRefetch },
      })

      // Navigate to members tab where GroupMembersPanel calls onMembersChange
      mockLocationValue = `/system-administration/access-management/groups/${VALID_GROUP_ID}/members`
      render(<GroupDetail />, { wrapper })

      // Trigger the onMembersChange callback via the mock button
      await user.click(screen.getByRole('button', { name: 'Trigger membership change' }))

      expect(mockMembersRefetch).toHaveBeenCalled()
    })
  })

  // ---- useQueryState onRetry callback ------------------------------------

  describe('useQueryState onRetry', () => {
    it('renders loading state via useQueryState when query is pending', () => {
      mockQueryByPath({
        '/groups/{group_id}': { isPending: true },
      })

      render(<GroupDetail />, { wrapper })

      // useQueryState returns loading state, rendered inside DetailPageShell
      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })
  })

  // ---- Accessibility ------------------------------------------------------

  describe('Accessibility', () => {
    it('has no accessibility violations on success state', async () => {
      const { container } = render(<GroupDetail />, { wrapper })

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        // Exclude aria-valid-attr-value: PatternFly Tabs generates aria-controls
        // referencing lazily-rendered tab panels that don't exist in the DOM yet
        results = await axe(container, {
          rules: { 'aria-valid-attr-value': { enabled: false } },
        })
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations on error state', async () => {
      mockQueryByPath({
        '/groups/{group_id}': { isError: true, error: new Error('Not found') },
      })

      const { container } = render(<GroupDetail />, { wrapper })
      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations for built-in group state', async () => {
      mockSuccessQueries({ ...mockGroup, is_builtin: true })
      const { container } = render(<GroupDetail />, { wrapper })

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container, {
          rules: { 'aria-valid-attr-value': { enabled: false } },
        })
      })
      expect(results!).toHaveNoViolations()
    })
  })

  describe('Permission-based tab gating', () => {
    function mockCanI(permissions: Record<string, boolean>) {
      vi.mocked(accessFetchClient.POST).mockImplementation((_path, opts) => {
        const body = (opts as { body?: { resource_type?: string } })?.body
        const resourceType = body?.resource_type ?? ''
        const allowed = permissions[resourceType] ?? true
        return Promise.resolve({ data: { allowed } } as never)
      })
    }

    it('hides Members tab when group:read is denied', async () => {
      mockCanI({ group: false })
      render(<GroupDetail />, { wrapper })

      await waitFor(() => {
        expect(screen.queryByRole('tab', { name: /Members/ })).not.toBeInTheDocument()
      })
      expect(screen.getByRole('tab', { name: /Details/ })).toBeInTheDocument()
    })

    it('hides Assignments tab when role-assignment:read is denied', async () => {
      mockCanI({ 'role-assignment': false })
      render(<GroupDetail />, { wrapper })

      await waitFor(() => {
        expect(screen.queryByRole('tab', { name: /Assignments/ })).not.toBeInTheDocument()
      })
      expect(screen.getByRole('tab', { name: /Members/ })).toBeInTheDocument()
    })

    it('always shows Details tab regardless of permissions', async () => {
      mockCanI({ group: false, 'role-assignment': false })
      render(<GroupDetail />, { wrapper })

      await waitFor(() => {
        expect(screen.queryByRole('tab', { name: /Members/ })).not.toBeInTheDocument()
      })
      expect(screen.getByRole('tab', { name: /Details/ })).toBeInTheDocument()
    })
  })
})
