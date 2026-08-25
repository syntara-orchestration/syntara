import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { adminClient, authFetchClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { routerTestState, mockUseSearch } from '../../test/setup'
import { accessClient } from '../access/accessClient'

import { UsersTab } from './UsersTab'

// Mock dependencies
vi.mock('../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  adminClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authFetchClient: {
    GET: vi.fn().mockResolvedValue({ data: { resources: [] } }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('./useUserPermissions', () => ({
  useUserPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    canRevoke: true,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '', revoke: '' },
  }),
}))

// Create a QueryClient instance
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

describe('UsersTab Component', () => {
  const mockUsers = [
    {
      id: 'u1',
      username: 'admin',
      email: 'admin@example.com',
      first_name: 'Admin',
      last_name: 'User',
      is_enabled: true,
      is_builtin: true,
      auth_type: 'local' as const,
      auth_sources: ['Local'],
      last_login: '2024-03-15T10:30:00Z',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
    },
    {
      id: 'u2',
      username: 'jdoe',
      email: 'jdoe@example.com',
      first_name: 'John',
      last_name: 'Doe',
      is_enabled: true,
      auth_type: 'federated' as const,
      auth_sources: ['AAP', 'Azure AD'],
      last_login: '2024-03-14T08:00:00Z',
      created_at: '2024-02-01T00:00:00Z',
      updated_at: '2024-02-02T00:00:00Z',
    },
    {
      id: 'u3',
      username: 'viewer1',
      email: 'viewer@example.com',
      first_name: 'View',
      last_name: 'Only',
      is_enabled: false,
      auth_type: 'local' as const,
      auth_sources: ['Local'],
      last_login: null,
      created_at: '2024-03-01T00:00:00Z',
      updated_at: '2024-03-02T00:00:00Z',
    },
  ]

  const mockGroupsData = {
    resources: [
      {
        id: 'g0-builtin-admins',
        name: 'admins',
        description: 'Built-in administrators group',
        is_builtin: true,
        member_count: 1,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ],
  }

  beforeEach(() => {
    mockUseSearch.mockReturnValue({})

    vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
      const endpoint = args[1] as string
      if (endpoint === '/groups') {
        return {
          data: mockGroupsData,
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
      if (endpoint === '/groups/{group_id}/members') {
        return {
          data: { resources: [mockUsers[0]] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
      return {
        data: { resources: mockUsers },
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

    vi.mocked(adminClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  describe('Built-in Administrator Account', () => {
    it('renders the Built-in Administrator Account card', () => {
      render(<UsersTab />, { wrapper })

      expect(screen.getByText('Built-in Administrator Account')).toBeInTheDocument()
      expect(screen.getByText(/Username:/)).toBeInTheDocument()
    })

    it('renders the admin account switch as checked when admin is active', () => {
      render(<UsersTab />, { wrapper })

      const adminSwitch = screen.getByRole('switch', {
        name: /Built-in administrator account enabled/,
      })
      expect(adminSwitch).toBeChecked()
      expect(adminSwitch).toBeDisabled()
    })

    it('does not render admin card when no builtin user exists', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const endpoint = args[1] as string
        if (endpoint === '/groups') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        if (endpoint === '/groups/{group_id}/members') {
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
          data: { resources: [mockUsers[1], mockUsers[2]] },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UsersTab />, { wrapper })

      expect(screen.queryByText('Built-in Administrator Account')).not.toBeInTheDocument()
      expect(screen.getByText('jdoe')).toBeInTheDocument()
    })

    it('renders the admin account switch as unchecked when admin is inactive', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: [{ ...mockUsers[0], is_enabled: false }, mockUsers[1], mockUsers[2]],
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      const adminSwitch = screen.getByRole('switch', {
        name: /Built-in administrator account disabled/,
      })
      expect(adminSwitch).not.toBeChecked()
      expect(adminSwitch).toBeEnabled()
    })
  })

  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()
    })

    it('renders users in table', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      expect(within(table).getByText('admin')).toBeInTheDocument()
      expect(within(table).getByText('jdoe')).toBeInTheDocument()
      expect(within(table).getByText('viewer1')).toBeInTheDocument()
    })

    it('renders table columns with correct data', () => {
      render(<UsersTab />, { wrapper })

      expect(screen.getByText('Admin User')).toBeInTheDocument()
      expect(screen.getByText('admin@example.com')).toBeInTheDocument()
    })

    it('falls back to username in the name column when first_name is empty', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const endpoint = args[1] as string
        if (endpoint === '/groups' || endpoint === '/groups/{group_id}/members') {
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
          data: {
            resources: [
              {
                ...mockUsers[2],
                username: 'noname',
                first_name: '',
                last_name: null,
                email: 'noname@example.com',
              },
            ],
          },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      expect(within(table).getAllByText('noname')).toHaveLength(2)
    })

    it('renders last login as dash for null', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')
      const viewer1Row = rows[3]
      expect(within(viewer1Row).getByText('-')).toBeInTheDocument()
    })
  })

  describe('Authentication Column', () => {
    it('renders Authentication column header', () => {
      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('columnheader', { name: 'Authentication' })).toBeInTheDocument()
    })

    it('renders Local label for local auth users', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')
      // rows[1] is admin (local)
      expect(within(rows[1]).getByText('Local')).toBeInTheDocument()
    })

    it('renders multiple auth source labels for federated users', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')
      // rows[2] is jdoe (federated with AAP and Azure AD)
      expect(within(rows[2]).getByText('AAP')).toBeInTheDocument()
      expect(within(rows[2]).getByText('Azure AD')).toBeInTheDocument()
    })

    it('renders both local and federated auth source labels across rows', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')

      // Admin (local) has exactly one label: Local
      expect(within(rows[1]).getByText('Local')).toBeInTheDocument()

      // jdoe (federated) has two labels: AAP and Azure AD
      expect(within(rows[2]).getByText('AAP')).toBeInTheDocument()
      expect(within(rows[2]).getByText('Azure AD')).toBeInTheDocument()
      expect(within(rows[2]).queryByText('Local')).not.toBeInTheDocument()

      // viewer1 (local) also has Local
      expect(within(rows[3]).getByText('Local')).toBeInTheDocument()
    })

    it('falls back to Local label when auth_sources is undefined', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const endpoint = args[1] as string
        if (endpoint === '/groups') {
          return {
            data: mockGroupsData,
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        if (endpoint === '/groups/{group_id}/members') {
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
          data: {
            resources: [
              {
                id: 'u-no-sources',
                username: 'nosources',
                email: 'no@example.com',
                first_name: 'No',
                last_name: 'Sources',
                is_enabled: true,
                last_login: null,
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ],
          },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      })

      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      expect(within(table).getByText('Local')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<UsersTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Empty State', () => {
    it('displays empty state when no users exist and no filters active', () => {
      vi.mocked(accessClient.useQuery).mockReturnValueOnce({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      expect(screen.getByText('No users yet')).toBeInTheDocument()
      expect(screen.getByText('Create a user to manage access to the platform.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays loading state', () => {
      vi.mocked(accessClient.useQuery).mockReturnValueOnce({
        data: null,
        isPending: true,
        isError: false,
        error: null,
      })

      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })

    it('displays error state', () => {
      const mockError = new Error('Failed to load users')
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: null,
        isPending: false,
        isError: true,
        error: mockError,
      })

      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('renders username filter input', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /username filter/i })
      await user.type(textInput, 'admin')
      expect(textInput).toHaveValue('admin')
    })

    it('applies username filter to URL params on submit', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /username filter/i })
      await user.type(textInput, 'admin')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        // useCursorPagination uses history.push to update URL params
        expect(routerTestState.historyPush).toHaveBeenCalled()
        const lastCall = routerTestState.historyPush.mock.calls.at(-1)?.[0] as string
        expect(decodeURIComponent(lastCall)).toContain('username[contains]=admin')
      })
    })

    it('sends auth_source query param when authentication source filter is in the URL', async () => {
      routerTestState.searchStr = '?auth_source=Local'
      render(<UsersTab />, { wrapper })

      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams?.auth_source).toBe('Local')
        expect(queryParams?.auth_type).toBeUndefined()
      })
    })

    it('sends auth_source query param for a federated provider filter', async () => {
      routerTestState.searchStr = '?auth_source=AAP'
      render(<UsersTab />, { wrapper })

      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams?.auth_source).toBe('AAP')
      })
    })

    it('applies authentication source filter from UI to URL and API query', async () => {
      vi.mocked(authFetchClient.GET).mockResolvedValueOnce({
        data: {
          resources: [
            { id: '1', name: 'AAP', provider_type: 'oidc', provider_template: null },
            { id: '2', name: 'Azure AD', provider_type: 'oidc', provider_template: null },
          ],
        },
      } as never)

      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const filterBar = screen.getByRole('search', { name: 'Filters' })
      await user.click(within(filterBar).getByRole('button', { name: 'Username' }))
      await user.click(await screen.findByRole('option', { name: 'Authentication' }))

      const valueSelector = within(filterBar).getByRole('button', { name: /Filter by authentication/i })
      await user.click(valueSelector)
      await user.click(await screen.findByRole('option', { name: 'AAP' }))

      await waitFor(() => {
        expect(routerTestState.historyPush).toHaveBeenCalled()
        const lastCall = routerTestState.historyPush.mock.calls.at(-1)?.[0] as string
        expect(lastCall).toContain('auth_source=AAP')
      })
    })
  })

  describe('Sorting Functionality', () => {
    it('renders sortable column headers', () => {
      render(<UsersTab />, { wrapper })

      const usernameHeader = screen.getByRole('columnheader', { name: /Username/i })
      expect(within(usernameHeader).getByRole('button')).toBeInTheDocument()

      const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
      expect(within(nameHeader).getByRole('button')).toBeInTheDocument()
    })

    it('sorts by Username ascending by default', () => {
      render(<UsersTab />, { wrapper })

      // Server-side sorting: data is rendered in the order returned by the mock
      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')
      expect(within(rows[1]).getByText('admin')).toBeInTheDocument()
      expect(within(rows[2]).getByText('jdoe')).toBeInTheDocument()
      expect(within(rows[3]).getByText('viewer1')).toBeInTheDocument()
    })

    it('sorts by Username descending when toggling sort direction', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const usernameHeader = screen.getByRole('columnheader', { name: /Username/i })
      const sortButton = within(usernameHeader).getByRole('button')
      await user.click(sortButton)

      // Server-side sorting: verify the sort param was sent to the API
      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort')
      })
    })
  })

  describe('Pagination', () => {
    it('displays pagination controls when next cursor is available', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers, next: 'next-cursor-abc', prev: null, total: 25 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      // PF Pagination renders "Go to next page" / "Go to previous page" aria-labels
      expect(screen.getByRole('button', { name: /next/i })).not.toBeDisabled()
    })

    it('displays total count when available', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers, next: 'next-cursor', prev: null, total: 25 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /of 25/i })).toBeInTheDocument()
    })

    it('displays singular "user" when only one result', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [mockUsers[0]], next: null, prev: null, total: 1 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /\bof 1\b/i })).toBeInTheDocument()
    })
  })

  describe('Navigation', () => {
    it('navigates to create user page when Create user is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /create user/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users/create',
      })
    })

    it('navigates to edit user page when edit action is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const editOption = await screen.findByRole('menuitem', { name: /edit/i })
      await user.click(editOption)

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users/u2/edit',
      })
    })

    it('renders username as a link to user detail page', () => {
      render(<UsersTab />, { wrapper })

      const usernameLink = screen.getByRole('link', { name: 'admin' })
      expect(usernameLink).toHaveAttribute('href', '/system-administration/access-management/users/u1')
    })
  })

  describe('Row Actions', () => {
    it('does not show actions for the admin user', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      const rows = within(table).getAllByRole('row')
      // rows[0] is header, rows[1] is admin (u1), rows[2] is jdoe, rows[3] is viewer1
      const adminRow = rows[1]
      const nonAdminRow = rows[2]

      expect(within(adminRow).queryByRole('button', { name: 'Kebab toggle' })).not.toBeInTheDocument()
      expect(within(nonAdminRow).getByRole('button', { name: 'Kebab toggle' })).toBeInTheDocument()
    })

    it('opens delete dialog when delete action is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete user?')).toBeInTheDocument()
      })

      // Verify the username renders in the dialog body (covers deleteDialog.item?.username branch)
      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText('jdoe')).toBeInTheDocument()
      expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument()
      expect(
        screen.getByRole('checkbox', { name: 'I understand this user will be permanently deleted.' })
      ).toBeInTheDocument()
    })
  })

  describe('Delete Dialog Flow', () => {
    it('calls delete mutation when Delete button is clicked', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await user.click(screen.getByRole('checkbox'))
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      expect(mockDeleteMutate).toHaveBeenCalled()
      const callArgs = mockDeleteMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({ params: { path: { user_id: 'u2' } } })
    })

    it('shows success alert and closes dialog on successful delete', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn().mockResolvedValue({})

      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await user.click(screen.getByRole('checkbox'))
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      const callbacks = mockDeleteMutate.mock.calls[0][1] as { onSuccess: () => void; onSettled: () => void }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Delete user?')).not.toBeInTheDocument()
      })
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('closes delete dialog when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete user?')).toBeInTheDocument()
      })

      const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' })
      await user.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText(/This action cannot be undone/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Delete Dialog Error Handling', () => {
    it('shows error alert on delete failure', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<UsersTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await user.click(screen.getByRole('checkbox'))
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onError: (error: unknown) => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError(new Error('Server error'))
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Delete user?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Pagination Navigation', () => {
    it('renders PF Pagination with next/prev buttons when cursors are available', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: mockUsers, next: 'next-cursor-abc', prev: null, total: 25 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<UsersTab />, { wrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      const prevButton = within(paginationNav).getByRole('button', { name: 'Go to previous page' })
      expect(nextButton).not.toBeDisabled()
      expect(prevButton).toBeDisabled()
    })
  })

  describe('Filter Empty State', () => {
    it('shows filter empty state when no results with active filters', () => {
      // Simulate active filters via URL params
      routerTestState.searchStr = '?username%5Bcontains%5D=nonexistent'

      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const endpoint = args[1] as string
        if (endpoint === '/groups' || endpoint === '/groups/{group_id}/members') {
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

      render(<UsersTab />, { wrapper })

      expect(screen.getByText('No results found')).toBeInTheDocument()
    })

    it('updates URL params when filter is applied', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /username filter/i })
      await user.type(textInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(routerTestState.historyPush).toHaveBeenCalled()
        const lastCall = routerTestState.historyPush.mock.calls.at(-1)?.[0] as string
        expect(decodeURIComponent(lastCall)).toContain('username[contains]=nonexistent')
      })
    })
  })

  describe('Sorting by other columns', () => {
    it('sorts by Name when Name column is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
      const sortButton = within(nameHeader).getByRole('button')
      await user.click(sortButton)

      // Server-side sorting: verify sort param is sent
      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', 'first_name')
      })
    })

    it('sorts by Email when Email column is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const emailHeader = screen.getByRole('columnheader', { name: /Email/i })
      const sortButton = within(emailHeader).getByRole('button')
      await user.click(sortButton)

      // Server-side sorting: verify sort param is sent
      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', 'email')
      })
    })

    it('sorts by Last login when Last login column is clicked', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      const loginHeader = screen.getByRole('columnheader', { name: /Last login/i })
      const sortButton = within(loginHeader).getByRole('button')
      await user.click(sortButton)

      // Server-side sorting: verify sort param is sent
      await waitFor(() => {
        const lastCall = vi
          .mocked(accessClient.useQuery)
          .mock.calls.filter((c) => c[1] === '/users')
          .at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', 'last_login')
      })
    })
  })

  describe('State column', () => {
    it('renders State column header and per-user switches', () => {
      render(<UsersTab />, { wrapper })

      expect(screen.getByRole('columnheader', { name: 'State' })).toBeInTheDocument()
      expect(screen.getByRole('switch', { name: 'Toggle jdoe status' })).toBeChecked()
      expect(screen.getByRole('switch', { name: 'Toggle viewer1 status' })).not.toBeChecked()
      expect(screen.getByRole('switch', { name: 'Toggle admin status' })).toBeChecked()
    })

    it('opens disable confirmation when toggling an enabled user off', async () => {
      const user = userEvent.setup()
      render(<UsersTab />, { wrapper })

      await user.click(screen.getByRole('switch', { name: 'Toggle jdoe status' }))

      expect(screen.getByRole('heading', { name: 'Disable user?' })).toBeInTheDocument()
      expect(screen.getByText(/will be disabled and will no longer be able to sign in/i)).toBeInTheDocument()
    })

    it('does not show DisabledBadge next to usernames', () => {
      render(<UsersTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Users' })
      expect(within(table).queryByText('Disabled')).not.toBeInTheDocument()
    })
  })
})
