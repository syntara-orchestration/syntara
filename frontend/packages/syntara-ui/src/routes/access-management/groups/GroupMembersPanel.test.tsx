import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { searchParamsMock } from '../../../test/searchParamsMock'
import { accessClient } from '../../access/accessClient'
import { useAllUsers } from '../../access/useAllUsers'

import { GroupMembersPanel } from './GroupMembersPanel'

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

vi.mock('../../access/useAllUsers', () => ({
  useAllUsers: vi.fn(),
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockMembers = [
  {
    id: 'u1',
    username: 'alice',
    first_name: 'Alice',
    last_name: 'Smith',
    email: 'alice@example.com',
    membership_sources: [{ type: 'manual' }],
  },
  {
    id: 'u2',
    username: 'bob',
    first_name: 'Bob',
    last_name: 'Jones',
    email: 'bob@example.com',
    membership_sources: [{ type: 'idp', provider_name: 'Azure AD' }],
  },
]

describe('GroupMembersPanel', () => {
  const defaultProps = {
    groupId: 'group-123',
    onMembershipChange: vi.fn(),
  }

  beforeEach(() => {
    // Reset URL search params so filter state from previous tests doesn't leak
    window.history.replaceState({}, '', window.location.pathname)
    searchParamsMock.reset()

    vi.mocked(useAllUsers).mockReturnValue({
      users: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: mockMembers },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn().mockResolvedValue({}),
    } as never)

    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  describe('Rendering', () => {
    it('renders members table with data', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('grid', { name: 'Group members table' })).toBeInTheDocument()
      expect(screen.getByText('alice')).toBeInTheDocument()
      expect(screen.getByText('bob')).toBeInTheDocument()
    })

    it('links usernames to user detail pages', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('link', { name: 'alice' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/users/u1'
      )
      expect(screen.getByRole('link', { name: 'bob' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/users/u2'
      )
    })

    it('renders table column headers', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('columnheader', { name: 'Username' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Email' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Source' })).toBeInTheDocument()
    })

    it('displays member details in rows', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Alice Smith')).toBeInTheDocument()
      expect(screen.getByText('alice@example.com')).toBeInTheDocument()
      expect(screen.getByText('Bob Jones')).toBeInTheDocument()
      expect(screen.getByText('bob@example.com')).toBeInTheDocument()
    })

    it('falls back to username in the name column when first_name is empty', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: [
            {
              id: 'u3',
              username: 'noname',
              first_name: '',
              last_name: null,
              email: 'noname@example.com',
              membership_sources: [{ type: 'manual' }],
            },
          ],
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('link', { name: 'noname' })).toBeInTheDocument()
      expect(screen.getAllByText('noname')).toHaveLength(2)
    })

    it('shows source labels for membership sources', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Manual')).toBeInTheDocument()
      expect(screen.getByText('Azure AD')).toBeInTheDocument()
    })

    it('renders Add member button', () => {
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('button', { name: /add member/i })).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('shows empty state when no members', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('No members yet')).toBeInTheDocument()
      expect(screen.getByText(/add users to this group/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /add member/i })).toBeInTheDocument()
    })
  })

  describe('Loading state', () => {
    it('shows loading state when query is pending', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: null,
        isPending: true,
        isError: false,
        error: null,
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('shows error state on error', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: null,
        isPending: false,
        isError: true,
        error: new Error('Failed'),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error loading members' })).toBeInTheDocument()
    })
  })

  describe('Filtering', () => {
    it('filters members by username', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      // The filter bar defaults to "Username" field
      const filterInput = screen.getByPlaceholderText('Filter by username')
      await user.type(filterInput, 'alice')
      await user.keyboard('{Enter}')

      const table = screen.getByRole('grid', { name: 'Group members table' })
      await waitFor(() => {
        expect(within(table).getByText('alice')).toBeInTheDocument()
        expect(within(table).queryByText('bob')).not.toBeInTheDocument()
      })
    })

    it('shows empty filter state when no results match', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      const nameInput = screen.getByPlaceholderText('Filter by username')
      await user.type(nameInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })
  })

  describe('Remove member', () => {
    it('opens remove confirmation dialog', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[1]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      await waitFor(() => {
        expect(screen.getByText('Remove member?')).toBeInTheDocument()
        expect(screen.getByText(/This removes/i)).toBeInTheDocument()
      })
    })

    it('calls removeMember mutation on confirm', async () => {
      const mockMutate = vi.fn((_params: unknown, callbacks?: { onSuccess?: () => void; onSettled?: () => void }) => {
        callbacks?.onSuccess?.()
        callbacks?.onSettled?.()
      })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      } as never)

      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      // Open actions menu
      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[1]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      // Confirm removal
      const removeButton = screen.getByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })
    })

    it('closes remove dialog when cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      // Open actions menu
      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[1]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      // Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Remove member?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Pagination', () => {
    it('paginates when more than 20 members', async () => {
      const user = userEvent.setup()
      const manyMembers = Array.from({ length: 25 }, (_, i) => ({
        id: `u-${i}`,
        username: `user-${i}`,
        first_name: `User`,
        last_name: `${i}`,
        email: `user${i}@example.com`,
        membership_sources: [{ type: 'manual' }],
      }))

      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: manyMembers },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      // First page shows first 20
      expect(screen.getByText('user-0')).toBeInTheDocument()
      expect(screen.getByText('user-19')).toBeInTheDocument()
      expect(screen.queryByText('user-20')).not.toBeInTheDocument()

      // Go to next page
      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.getByText('user-20')).toBeInTheDocument()
        expect(screen.queryByText('user-0')).not.toBeInTheDocument()
      })
    })
  })

  describe('Add member', () => {
    it('opens add member modal when Add member button is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /add member/i }))

      await waitFor(() => {
        // The modal should be visible - look for the modal header or content
        const addTexts = screen.getAllByText(/add member/i)
        expect(addTexts.length).toBeGreaterThanOrEqual(2) // button + modal header
      })
    })

    it('opens add member modal from empty state', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /add member/i }))

      await waitFor(() => {
        const addTexts = screen.getAllByText(/add member/i)
        expect(addTexts.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('shows a display name in the typeahead and omits it when the user has no name', async () => {
      vi.mocked(useAllUsers).mockReturnValue({
        users: [
          {
            id: 'u-named',
            username: 'dana',
            first_name: 'Dana',
            last_name: 'Lee',
            email: 'dana@example.com',
            is_enabled: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 'u-noname',
            username: 'noname',
            first_name: '',
            last_name: null,
            email: 'nn@example.com',
            is_enabled: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /add member/i }))
      await user.click(screen.getByPlaceholderText('Search for a user...'))

      expect(await screen.findByText('Dana Lee')).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /dana/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /^noname$/i })).toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /noname.*Dana Lee/i })).not.toBeInTheDocument()
    })
  })

  describe('Remove member error handling', () => {
    it('shows error alert when remove fails', async () => {
      const mockMutate = vi.fn(
        (_params: unknown, callbacks?: { onError?: (err: unknown) => void; onSettled?: () => void }) => {
          callbacks?.onError?.(new Error('Remove failed'))
          callbacks?.onSettled?.()
        }
      )
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      } as never)

      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[1]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      const removeButton = screen.getByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      await waitFor(() => {
        expect(screen.getByText('Failed to remove member')).toBeInTheDocument()
      })
    })

    it('calls onMembershipChange after successful removal', async () => {
      const onMembershipChange = vi.fn()
      const mockMutate = vi.fn((_params: unknown, callbacks?: { onSuccess?: () => void; onSettled?: () => void }) => {
        callbacks?.onSuccess?.()
        callbacks?.onSettled?.()
      })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      } as never)

      const user = userEvent.setup()
      render(<GroupMembersPanel groupId="group-123" onMembershipChange={onMembershipChange} />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      const actionsButtons = within(rows[1]).getAllByRole('button')
      await user.click(actionsButtons[actionsButtons.length - 1])

      const removeItem = await screen.findByText('Remove')
      await user.click(removeItem)

      const removeButton = screen.getByRole('button', { name: 'Remove' })
      await user.click(removeButton)

      await waitFor(() => {
        expect(onMembershipChange).toHaveBeenCalled()
      })
    })
  })

  describe('Disabled and builtin members', () => {
    it('shows disabled badge for disabled members', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: [
            {
              id: 'u3',
              username: 'charlie',
              first_name: 'Charlie',
              last_name: 'Brown',
              email: 'charlie@example.com',
              is_enabled: false,
              membership_sources: [{ type: 'manual' }],
            },
          ],
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn().mockResolvedValue({}),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Disabled')).toBeInTheDocument()
    })

    it('hides actions for builtin members', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: {
          resources: [
            {
              id: 'u4',
              username: 'system',
              first_name: 'System',
              last_name: 'User',
              email: 'system@example.com',
              is_builtin: true,
              membership_sources: [{ type: 'manual' }],
            },
          ],
        },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn().mockResolvedValue({}),
      } as never)

      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      const table = screen.getByRole('grid', { name: 'Group members table' })
      const rows = within(table).getAllByRole('row')
      // Header + 1 data row
      expect(rows).toHaveLength(2)
      // No kebab/action button in the data row
      expect(within(rows[1]).queryByRole('button')).not.toBeInTheDocument()
    })
  })

  describe('Clear all filters', () => {
    it('clears filters from empty filter state', async () => {
      const user = userEvent.setup()
      render(<GroupMembersPanel {...defaultProps} />, { wrapper })

      // Apply a filter that yields no results
      const nameInput = screen.getByPlaceholderText('Filter by username')
      await user.type(nameInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })

      // Click "Clear all filters" — there may be multiple; click the last one (empty state)
      const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i })
      await user.click(clearButtons[clearButtons.length - 1])

      await waitFor(() => {
        expect(screen.getByText('alice')).toBeInTheDocument()
        expect(screen.getByText('bob')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with member data', async () => {
      const { container } = render(<GroupMembersPanel {...defaultProps} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)

      const { container } = render(<GroupMembersPanel {...defaultProps} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
