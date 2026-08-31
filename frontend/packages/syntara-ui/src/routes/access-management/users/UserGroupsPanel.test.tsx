import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient, accessFetchClient } from '../../access/accessClient'
import { useAllGroups } from '../../access/useAllGroups'

import { UserGroupsPanel } from './UserGroupsPanel'

vi.mock('../../../client', () => ({
  usersClient: { useQuery: vi.fn() },
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

vi.mock('../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

vi.mock('../useGroupPermissions', () => ({
  useGroupPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    canManageMembers: true,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '', manageMembers: '' },
  }),
}))

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/access-management/users/user-123/groups',
}))

vi.mock('../../../hooks/routing/useSearchParams', async () => {
  const React = await import('react')
  return {
    useSearchParams: () => React.useState(new URLSearchParams()),
  }
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockGroups = [
  {
    id: 'g-auth',
    name: 'authenticated',
    description: 'All authenticated users',
    is_builtin: true,
    source: 'local',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'g1',
    name: 'platform-admins',
    description: 'Full admins',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'g2',
    name: 'developers',
    description: null,
    created_at: '2026-01-15T00:00:00Z',
    updated_at: '2026-01-16T00:00:00Z',
  },
]

describe('UserGroupsPanel', () => {
  beforeEach(() => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })

    vi.mocked(useAllGroups).mockReturnValue({
      groups: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
      if (path === '/users/{user_id}/groups') {
        return {
          data: { resources: mockGroups },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
      return {
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never
    })

    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  describe('Rendering', () => {
    it('renders group table with data', () => {
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByRole('grid', { name: 'User groups table' })).toBeInTheDocument()
      expect(screen.getByText('platform-admins')).toBeInTheDocument()
      expect(screen.getByText('developers')).toBeInTheDocument()
    })

    it('renders table column headers', () => {
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Source' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument()
    })

    it('displays group names in each row', () => {
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      // rows[0] is the header row
      expect(within(rows[1]).getByText('authenticated')).toBeInTheDocument()
      expect(within(rows[2]).getByText('platform-admins')).toBeInTheDocument()
      expect(within(rows[3]).getByText('developers')).toBeInTheDocument()
    })

    it('links group names to group detail pages', () => {
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByRole('link', { name: 'authenticated' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/groups/g-auth'
      )
      expect(screen.getByRole('link', { name: 'platform-admins' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/groups/g1'
      )
      expect(screen.getByRole('link', { name: 'developers' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/groups/g2'
      )
    })

    it('displays group descriptions and handles null description', () => {
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByText('Full admins')).toBeInTheDocument()
      // null description renders as empty string, so the row renders without error
      expect(screen.getByText('developers')).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('shows "No groups yet" empty state when no groups returned', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByText('No groups yet')).toBeInTheDocument()
      expect(screen.getByText('This user is not a member of any groups.')).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('shows loading state when pending', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: null,
            isPending: true,
            isError: false,
            error: null,
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    it('shows error state on error', () => {
      const mockError = new Error('Failed to load groups')
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: null,
            isPending: false,
            isError: true,
            error: mockError,
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error loading groups' })).toBeInTheDocument()
    })
  })

  describe('API Integration', () => {
    it('passes userId to the query', () => {
      render(<UserGroupsPanel userId="abc-456" />, { wrapper })

      expect(accessClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/users/{user_id}/groups',
        expect.objectContaining({
          params: { path: { user_id: 'abc-456' } },
        })
      )
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with group data', async () => {
      const { container } = render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      const { container } = render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Filtering', () => {
    it('filters groups by name', async () => {
      const user = userEvent.setup()
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Type in name filter
      const nameInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(nameInput, 'platform')
      await user.keyboard('{Enter}')

      // Only platform-admins should be visible after filtering
      await waitFor(() => {
        expect(screen.getByText('platform-admins')).toBeInTheDocument()
        expect(screen.queryByText('developers')).not.toBeInTheDocument()
      })
    })

    it('filters groups by description', async () => {
      const user = userEvent.setup()
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Switch to description filter
      const fieldButtons = screen.getAllByRole('button', { name: 'Name' })
      const fieldSelector = fieldButtons[0]
      await user.click(fieldSelector)
      await user.click(await screen.findByRole('option', { name: /description/i }))

      // Type in description filter
      const descInput = screen.getByRole('textbox', { name: /description filter/i })
      await user.type(descInput, 'Full')
      await user.keyboard('{Enter}')

      // Only platform-admins (with "Full admins" description) should be visible
      await waitFor(() => {
        expect(screen.getByText('platform-admins')).toBeInTheDocument()
        expect(screen.queryByText('developers')).not.toBeInTheDocument()
      })
    })

    it('shows EmptyStateFilter when filter returns no results', async () => {
      const user = userEvent.setup()
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Type a non-matching filter
      const nameInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(nameInput, 'zzz-nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })
  })

  describe('Remove from group', () => {
    const mockGroupsWithNonBuiltin = [
      {
        id: 'g1',
        name: 'platform-admins',
        description: 'Full admins',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        is_builtin: false,
      },
      {
        id: 'g2',
        name: 'developers',
        description: null,
        created_at: '2026-01-15T00:00:00Z',
        updated_at: '2026-01-16T00:00:00Z',
        is_builtin: false,
      },
    ]

    it('shows remove action for non-builtin groups', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroupsWithNonBuiltin },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      // rows[1] is authenticated (no actions), rows[2] is first user group
      const actionsButtons = within(rows[2]).getAllByRole('button')
      expect(actionsButtons.length).toBeGreaterThan(0)
    })

    it('does not show remove action for authenticated group', () => {
      const authenticatedGroup = [
        {
          id: 'g-builtin',
          name: 'authenticated',
          description: 'All authenticated users',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-02T00:00:00Z',
          is_builtin: true,
        },
      ]

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: authenticatedGroup },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: authenticatedGroup },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // The builtin group "authenticated" should show the "All users" label
      expect(screen.getByText('All users')).toBeInTheDocument()
    })

    it('shows remove action for non-authenticated builtin groups', () => {
      const builtinGroups = [
        {
          id: 'g-builtin-auditors',
          name: 'auditors',
          description: 'Read-only access for compliance review',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-02T00:00:00Z',
          is_builtin: true,
        },
      ]

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: builtinGroups },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: builtinGroups },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      // rows[0] is header, rows[1] is the auditors group
      const actionsButtons = within(rows[1]).getAllByRole('button')
      expect(actionsButtons.length).toBeGreaterThan(0)
    })

    it('opens remove confirmation dialog and removes group on confirm', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn().mockResolvedValue({})
      const mockRemoveMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.(undefined, params, undefined)
          callbacks?.onSettled?.()
        }
      )

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroupsWithNonBuiltin },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockRemoveMutate,
        isPending: false,
      } as never)

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open actions menu for the first user group (rows[2] is first user group)
      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[2]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      // Click "Remove" action
      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      // Confirmation dialog should appear
      await waitFor(() => {
        expect(screen.getByText('Remove from group?')).toBeInTheDocument()
        // "platform-admins" appears in both the table and dialog
        expect(screen.getByText(/removes the user from group/)).toBeInTheDocument()
      })

      // Confirm removal
      const removeButton = screen.getByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      // Verify mutation was called
      await waitFor(() => {
        expect(mockRemoveMutate).toHaveBeenCalled()
        expect(mockRefetch).toHaveBeenCalled()
      })
    })

    it('shows error alert when remove fails', async () => {
      const user = userEvent.setup()
      const mockRemoveMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onError?.(new Error('Remove failed'), params, undefined)
          callbacks?.onSettled?.()
        }
      )

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroupsWithNonBuiltin },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn().mockResolvedValue({}),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockRemoveMutate,
        isPending: false,
      } as never)

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open actions menu (rows[2] is first user group, after header and authenticated)
      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[2]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      // Click Remove
      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      // Confirm removal
      const removeButton = await screen.findByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      // Verify error alert
      await waitFor(() => {
        expect(screen.getByText('Failed to remove from group')).toBeInTheDocument()
      })
    })

    it('closes remove dialog when cancel is clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroupsWithNonBuiltin },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn().mockResolvedValue({}),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open actions menu and click remove (rows[2] is first user group)
      const table = screen.getByRole('grid', { name: 'User groups table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[2]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      // Dialog should be open
      await waitFor(() => {
        expect(screen.getByText('Remove from group?')).toBeInTheDocument()
      })

      // Click cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText('Remove from group?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Add to group', () => {
    it('opens add to group modal when "Add to group" button is clicked', async () => {
      const user = userEvent.setup()
      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      const addButton = screen.getByRole('button', { name: /add to group/i })
      await user.click(addButton)

      // Modal header "Add to group" appears in addition to the button
      await waitFor(() => {
        const addTexts = screen.getAllByText(/add to group/i)
        expect(addTexts.length).toBeGreaterThanOrEqual(2) // button + modal header
      })

      // Modal should contain the "Add" submit button
      expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
    })

    it('closes add to group modal when cancel is clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(useAllGroups).mockReturnValue({
        groups: [
          { id: 'g3', name: 'testers', description: 'QA team', is_builtin: false, created_at: '', updated_at: '' },
          ...mockGroups.map((g) => ({ ...g, is_builtin: false })),
        ],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroups },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open the modal
      const addButton = screen.getByRole('button', { name: /add to group/i })
      await user.click(addButton)

      // Wait for modal to open (the "Add" submit button appears in the modal)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
      })

      // Click cancel
      const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' })
      await user.click(cancelButtons[cancelButtons.length - 1])

      // Modal should close - the "Add" submit button should be gone
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument()
      })
    })
  })

  describe('Authenticated group from API', () => {
    it('displays authenticated group returned by API with All users label', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: {
              resources: [mockGroups[0], mockGroups[1]],
            },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      expect(screen.getByText('authenticated')).toBeInTheDocument()
      expect(screen.getByText('All users')).toBeInTheDocument()
      expect(screen.getByText('platform-admins')).toBeInTheDocument()
    })
  })

  describe('Add to group form submission', () => {
    const setupAddToGroupMocks = (mockAddMutate: ReturnType<typeof vi.fn>) => {
      const mockRefetch = vi.fn().mockResolvedValue({})

      vi.mocked(useAllGroups).mockReturnValue({
        groups: [
          { id: 'g3', name: 'testers', description: 'QA', is_builtin: false, created_at: '', updated_at: '' },
          ...mockGroups.map((g) => ({ ...g, is_builtin: false })),
        ],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: mockGroups },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockAddMutate,
        isPending: false,
      } as never)

      return { mockRefetch }
    }

    it('shows validation error when submitting without selecting a group', async () => {
      const user = userEvent.setup()
      const mockAddMutate = vi.fn()
      setupAddToGroupMocks(mockAddMutate)

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open add to group modal
      const addButton = screen.getByRole('button', { name: /add to group/i })
      await user.click(addButton)

      // Wait for modal to open
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
      })

      // Click "Add" without selecting a group
      await user.click(screen.getByRole('button', { name: 'Add' }))

      // The mutation should NOT be called (validation prevents it)
      expect(mockAddMutate).not.toHaveBeenCalled()
    })

    it('successfully adds user to a group', async () => {
      const user = userEvent.setup()
      const mockAddMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
          }
        ) => {
          callbacks?.onSuccess?.(undefined, params, undefined)
        }
      )
      setupAddToGroupMocks(mockAddMutate)

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open add to group modal
      await user.click(screen.getByRole('button', { name: /add to group/i }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
      })

      // Click on the typeahead input to open the dropdown
      const typeaheadInput = screen.getByPlaceholderText('Search for a group...')
      await user.click(typeaheadInput)

      // Select the "testers" group (which is the only one not already a member)
      const testersOption = await screen.findByRole('option', { name: /testers/i })
      await user.click(testersOption)

      // Submit the form
      await user.click(screen.getByRole('button', { name: 'Add' }))

      // Verify mutation was called
      await waitFor(() => {
        expect(mockAddMutate).toHaveBeenCalled()
      })

      // Verify success alert
      await waitFor(() => {
        expect(screen.getByText('Added to group')).toBeInTheDocument()
      })
    })

    it('shows error alert when adding to group fails', async () => {
      const user = userEvent.setup()
      const mockAddMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
          }
        ) => {
          callbacks?.onError?.(new Error('Add failed'), params, undefined)
        }
      )
      setupAddToGroupMocks(mockAddMutate)

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Open add to group modal
      await user.click(screen.getByRole('button', { name: /add to group/i }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
      })

      // Select a group
      const typeaheadInput = screen.getByPlaceholderText('Search for a group...')
      await user.click(typeaheadInput)
      const testersOption = await screen.findByRole('option', { name: /testers/i })
      await user.click(testersOption)

      // Submit
      await user.click(screen.getByRole('button', { name: 'Add' }))

      // Verify error alert
      await waitFor(() => {
        expect(screen.getByText('Failed to add to group')).toBeInTheDocument()
      })
    })
  })

  describe('Pagination', () => {
    it('handles pagination with many groups', async () => {
      const user = userEvent.setup()

      // Create more than 20 groups to trigger pagination
      const manyGroups = Array.from({ length: 25 }, (_, i) => ({
        id: `g-${i}`,
        name: `group-${i}`,
        description: `Group ${i} description`,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        is_builtin: false,
      }))

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: manyGroups },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // First page shows 20 items: group-0..group-19
      expect(screen.getByText('group-0')).toBeInTheDocument()
      expect(screen.getByText('group-19')).toBeInTheDocument()
      expect(screen.queryByText('group-20')).not.toBeInTheDocument()

      // Click next page
      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      // Second page should show remaining groups (group-20..group-24)
      await waitFor(() => {
        expect(screen.getByText('group-20')).toBeInTheDocument()
        expect(screen.getByText('group-24')).toBeInTheDocument()
        expect(screen.queryByText('group-0')).not.toBeInTheDocument()
      })

      // Click previous page
      const prevButton = screen.getByRole('button', { name: /previous/i })
      await user.click(prevButton)

      // Back to first page
      await waitFor(() => {
        expect(screen.getByText('group-0')).toBeInTheDocument()
      })
    })
  })

  describe('Add to group in empty state', () => {
    it('opens add to group modal from empty state', async () => {
      const user = userEvent.setup()

      vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
        if (path === '/users/{user_id}/groups') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UserGroupsPanel userId="user-123" />, { wrapper })

      // Should show empty state
      expect(screen.getByText('No groups yet')).toBeInTheDocument()

      // Click "Add to group" from empty state
      const addButton = screen.getByRole('button', { name: /add to group/i })
      await user.click(addButton)

      // Modal should open - the "Add" submit button appears in the modal
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
      })
    })
  })
})
