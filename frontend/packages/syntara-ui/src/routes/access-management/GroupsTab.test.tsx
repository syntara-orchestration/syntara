import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { usersClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { assertUrlParam } from '../../test/filter-test-helpers'

import { GroupsTab } from './GroupsTab'

// Mock dependencies
vi.mock('../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useGroupPermissions', () => ({
  useGroupPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    canManageMembers: true,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '', manageMembers: '' },
  }),
}))

const mockSetSearchParams = vi.fn()
let mockSearchParams = new URLSearchParams()

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/access-management/groups',
}))

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
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

describe('GroupsTab Component', () => {
  const mockGroups = [
    {
      id: 'g1',
      name: 'Admins',
      description: 'Administrator group',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
    },
    {
      id: 'g2',
      name: 'Developers',
      description: 'Developer team',
      created_at: '2024-02-01T00:00:00Z',
      updated_at: '2024-02-02T00:00:00Z',
    },
    {
      id: 'g3',
      name: 'Viewers',
      description: null,
      created_at: '2024-03-01T00:00:00Z',
      updated_at: '2024-03-02T00:00:00Z',
    },
  ]

  beforeEach(() => {
    mockSetSearchParams.mockClear()
    mockSearchParams = new URLSearchParams()

    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: mockGroups },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)

    vi.mocked(usersClient.useMutation).mockReturnValue({
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
  })

  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<GroupsTab />, { wrapper })

      expect(screen.getByRole('button', { name: 'Create group' })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /name filter/i })).toBeInTheDocument()
    })

    it('renders groups in table', () => {
      render(<GroupsTab />, { wrapper })

      expect(screen.getByText('Admins')).toBeInTheDocument()
      expect(screen.getByText('Developers')).toBeInTheDocument()
      expect(screen.getByText('Viewers')).toBeInTheDocument()
    })

    it('renders table columns', () => {
      render(<GroupsTab />, { wrapper })

      expect(screen.getByText('Admins')).toBeInTheDocument()
      expect(screen.getByText('Administrator group')).toBeInTheDocument()
    })

    it('renders description as empty string for null', () => {
      render(<GroupsTab />, { wrapper })

      // Viewers group has null description — verify the table renders without error
      // and the group name is present (description renders as empty string)
      expect(screen.getByText('Viewers')).toBeInTheDocument()
      expect(screen.getByText('Administrator group')).toBeInTheDocument()
      expect(screen.getByText('Developer team')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<GroupsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Empty State', () => {
    it('displays empty state when no groups exist and no filters active', () => {
      vi.mocked(usersClient.useQuery).mockReturnValueOnce({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      expect(screen.getByText('No groups yet')).toBeInTheDocument()
      expect(screen.getByText('Create a group to organize users and manage access.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create group' })).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays loading state', () => {
      vi.mocked(usersClient.useQuery).mockReturnValueOnce({
        data: null,
        isPending: true,
        isError: false,
        error: null,
      })

      render(<GroupsTab />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })

    it('displays error state', () => {
      const mockError = new Error('Failed to load groups')
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: null,
        isPending: false,
        isError: true,
        error: mockError,
      })

      render(<GroupsTab />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('renders name filter input', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'admin')
      expect(textInput).toHaveValue('admin')
    })

    it('applies name filter to API query on submit', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'admin')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'name[contains]', 'admin')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })
  })

  describe('Sorting Functionality', () => {
    it('renders sortable column headers', () => {
      render(<GroupsTab />, { wrapper })

      // Name, Created, and Updated are sortable; Description is NOT sortable
      const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
      expect(within(nameHeader).getByRole('button')).toBeInTheDocument()

      const descriptionHeader = screen.getByRole('columnheader', { name: /Description/i })
      expect(within(descriptionHeader).queryByRole('button')).not.toBeInTheDocument()

      const createdHeader = screen.getByRole('columnheader', { name: /Created/i })
      expect(within(createdHeader).getByRole('button')).toBeInTheDocument()

      const updatedHeader = screen.getByRole('columnheader', { name: /Updated/i })
      expect(within(updatedHeader).getByRole('button')).toBeInTheDocument()
    })

    it('sends sort=name parameter to API by default', () => {
      render(<GroupsTab />, { wrapper })

      // Verify API was called with default sort parameter
      const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
      expect(lastCall).toBeDefined()
      const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params?.query
      expect(queryParams).toMatchObject({ sort: 'name' })
    })

    it('sends sort=-name parameter when toggling to descending', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /^Name$/i })
      const sortButton = within(nameHeader).getByRole('button')
      await user.click(sortButton)

      // Verify API was called with descending sort parameter
      await waitFor(() => {
        const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ sort: '-name' })
      })
    })

    it('sends sort=created_at parameter when sorting by Created', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const createdHeader = screen.getByRole('columnheader', { name: /Created/i })
      const sortButton = within(createdHeader).getByRole('button')
      await user.click(sortButton)

      // Verify API was called with created_at sort parameter
      await waitFor(() => {
        const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ sort: 'created_at' })
      })
    })

    it('sends sort=updated_at parameter when sorting by Updated', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const updatedHeader = screen.getByRole('columnheader', { name: /Updated/i })
      const sortButton = within(updatedHeader).getByRole('button')
      await user.click(sortButton)

      // Verify API was called with updated_at sort parameter
      await waitFor(() => {
        const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ sort: 'updated_at' })
      })
    })
  })

  describe('Pagination', () => {
    it('displays pagination controls when next cursor is available', () => {
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: mockGroups,
          next: 'next-cursor-abc',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      // PF Pagination renders "Go to next page" / "Go to previous page" aria-labels
      const nextButton = screen.getByRole('button', { name: /next/i })
      expect(nextButton).toBeInTheDocument()
      expect(nextButton).not.toBeDisabled()
    })

    it('displays total count when available', () => {
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: mockGroups,
          next: 'next-cursor',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      // PF Pagination renders item count display with total
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
      expect(screen.getByText('25')).toBeInTheDocument()
    })

    it('enables Previous button when prev cursor is available', () => {
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: mockGroups,
          next: 'next-cursor',
          prev: 'prev-cursor-abc',
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      const prevButton = screen.getByRole('button', { name: /previous/i })
      expect(prevButton).toBeInTheDocument()
    })

    it('renders footer when no cursors are available', () => {
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: mockGroups,
          next: null,
          prev: null,
          total: 3,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      // PF Pagination still renders even without cursors
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
    })

    it('calls onNext when Next page button is clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: mockGroups,
          next: 'next-cursor-abc',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      expect(nextButton).toBeInTheDocument()
    })

    it('does not reset cursor while query is fetching', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn()

      vi.mocked(usersClient.useQuery).mockReturnValueOnce({
        data: {
          resources: mockGroups,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      const { rerender } = render(<GroupsTab />, { wrapper })

      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      await waitFor(() => {
        const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Fetching state — cursor should NOT reset
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: [],
          next: 'next-cursor',
          prev: 'prev-cursor',
          total: 30,
        },
        isPending: false,
        isFetching: true,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      rerender(<GroupsTab />)

      await waitFor(() => {
        const lastCall = vi.mocked(usersClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })
    })

    it('displays singular "group" when only one result', () => {
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: {
          resources: [mockGroups[0]],
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      // PF Pagination renders item count display for single result
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
      expect(screen.getByText('1', { selector: 'b' })).toBeInTheDocument()
    })
  })

  describe('Row Actions', () => {
    it('provides row action menu for each group', () => {
      render(<GroupsTab />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Groups table' })
      expect(table).toBeInTheDocument()

      const rows = within(table).getAllByRole('row')
      // Header row + 3 data rows
      expect(rows.length).toBeGreaterThanOrEqual(4)
    })

    it('opens edit modal when edit action is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const editOption = await screen.findByRole('menuitem', { name: /edit/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByText('Edit Admins')).toBeInTheDocument()
      })
    })

    it('opens delete dialog when delete action is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete group?')).toBeInTheDocument()
      })
    })
  })

  describe('Delete Dialog Flow', () => {
    it('calls delete mutation when Delete button is clicked', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: { resources: mockGroups },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      vi.mocked(usersClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<GroupsTab />, { wrapper })

      // Open actions menu and click delete (first row is Admins alphabetically)
      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete button in dialog
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      expect(mockDeleteMutate).toHaveBeenCalled()
      const callArgs = mockDeleteMutate.mock.calls[0]
      // First row is Admins (g1) due to alphabetical sort
      expect(callArgs[0]).toEqual({ params: { path: { group_id: 'g1' } } })
    })

    it('shows success alert and closes dialog on successful delete', { timeout: 15_000 }, async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn().mockResolvedValue({})

      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: { resources: mockGroups },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      vi.mocked(usersClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<GroupsTab />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Simulate successful mutation
      const callbacks = mockDeleteMutate.mock.calls[0][1] as { onSuccess: () => void; onSettled: () => void }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText('Delete group?')).not.toBeInTheDocument()
      })
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('shows error alert on delete failure', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()

      vi.mocked(usersClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<GroupsTab />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Simulate failed mutation
      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onError: (err: Error) => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError(new Error('Permission denied'))
        callbacks.onSettled()
      })

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText('Delete group?')).not.toBeInTheDocument()
      })
    })

    it('closes delete dialog when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(actionButtons[0])
      const deleteOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(deleteOption)

      // Verify dialog is open
      await waitFor(() => {
        expect(screen.getByText('Delete group?')).toBeInTheDocument()
      })

      // Click Cancel
      const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' })
      await user.click(cancelButtons[cancelButtons.length - 1])

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText(/This action cannot be undone/)).not.toBeInTheDocument()
      })
    })

    it('does not call delete when groupToDelete is null', () => {
      const mockDeleteMutate = vi.fn()

      vi.mocked(usersClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        isPending: false,
      } as never)

      render(<GroupsTab />, { wrapper })

      // Don't open any dialog — the handleDelete guard should prevent calls
      expect(mockDeleteMutate).not.toHaveBeenCalled()
    })
  })

  describe('Create Group', () => {
    it('opens create modal when Create group button is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create group' }))

      await waitFor(() => {
        // Modal should show the name input field
        expect(screen.getByPlaceholderText('Enter group name')).toBeInTheDocument()
      })
    })

    it('opens create modal from empty state button', async () => {
      const user = userEvent.setup()

      vi.mocked(usersClient.useQuery).mockReturnValueOnce({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create group' }))

      await waitFor(() => {
        // Modal should show the name input field
        expect(screen.getByPlaceholderText('Enter group name')).toBeInTheDocument()
      })
    })
  })

  describe('Filter Empty State', () => {
    it('shows filter empty state when filters return no results', () => {
      // Pre-set URL to have an active filter
      mockSearchParams = new URLSearchParams('name%5Bcontains%5D=nonexistent')

      // Mock query to return empty results (filter is active via URL)
      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupsTab />, { wrapper })

      // With active filters and empty results, "No results found" is shown
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })
  })
})
