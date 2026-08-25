import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { useQueryState } from '../../components/states/useQueryState'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { AlertProvider } from '../../providers/alerts'
import { routerTestState } from '../../test/setup'

import { accessClient } from './accessClient'
import { RolesTab } from './RolesTab'
import type { RoleRead } from './types'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
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

vi.mock('./useProjectNameMap', () => ({
  useProjectNameMap: () => ({
    projectNameMap: new Map<string, string>(),
    isLoading: false,
  }),
}))

vi.mock('../../components/states/useQueryState', () => ({
  useQueryState: vi.fn(),
}))

vi.mock('../../hooks/invalidateAuthzCaches', () => ({
  invalidateAuthzCaches: vi.fn(),
}))

vi.mock('./useRolePermissions', () => ({
  useRolePermissions: () => mockUseRolePermissions(),
}))

const defaultRolePermissions = {
  canCreate: true,
  canUpdate: true,
  canDelete: true,
  isLoading: false,
  tooltips: {
    create: 'You need permission to create roles.',
    update: 'You need permission to update roles.',
    delete: 'You need permission to delete roles.',
  },
}

const mockUseRolePermissions = vi.hoisted(() => vi.fn(() => defaultRolePermissions))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function createWrapper(initialPath = '/system-administration/access-management/roles') {
  routerTestState.pathname = initialPath
  return function wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AlertProvider>{children}</AlertProvider>
      </QueryClientProvider>
    )
  }
}

const mockRoles: RoleRead[] = [
  {
    id: 'role-1',
    name: 'admin',
    description: 'Full admin access',
    policies: ['admin-policy', 'read-all'],
    is_builtin: true,
    is_system_scoped: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 'role-2',
    name: 'custom-editor',
    description: 'Custom editor role',
    policies: ['workflow-edit'],
    is_builtin: false,
    is_system_scoped: false,
    project_id: null,
    labels: {},
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-02T00:00:00Z',
  },
  {
    id: 'role-3',
    name: 'viewer',
    description: null,
    policies: null as unknown as string[],
    is_builtin: false,
    is_system_scoped: false,
    project_id: null,
    labels: {},
    created_at: '2024-03-01T00:00:00Z',
    updated_at: '2024-03-02T00:00:00Z',
  },
]

describe('RolesTab', () => {
  const mockRefetch = vi.fn().mockResolvedValue({})
  const mockDeleteMutate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    mockUseRolePermissions.mockImplementation(() => defaultRolePermissions)

    // Default: useQueryState returns null (success state)
    vi.mocked(useQueryState).mockReturnValue(null)

    vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
      if (path === '/projects') {
        return {
          data: [],
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: mockRefetch,
        } as never
      }
      return {
        data: { resources: mockRoles, next: null, total: 3 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never
    })

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
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with data', async () => {
      const { container } = render(<RolesTab />, { wrapper: createWrapper() })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [], next: null, total: 0 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      const { container } = render(<RolesTab />, { wrapper: createWrapper() })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders roles in table', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByText('admin')).toBeInTheDocument()
      expect(screen.getByText('custom-editor')).toBeInTheDocument()
      expect(screen.getByText('viewer')).toBeInTheDocument()
    })

    it('renders role descriptions', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByText('Full admin access')).toBeInTheDocument()
      expect(screen.getByText('Custom editor role')).toBeInTheDocument()
    })

    it('renders dash for null description', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const table = screen.getByRole('grid', { name: 'Roles' })
      const viewerRow = within(table)
        .getAllByRole('row')
        .find((row) => within(row).queryByText('viewer'))!
      const descriptionCell = within(viewerRow).getAllByRole('cell')[2]
      expect(descriptionCell).toHaveTextContent('-')
    })

    it('renders Built-in label for builtin roles', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByText('Built-in')).toBeInTheDocument()
    })

    it('renders Custom label for non-builtin roles', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const customLabels = screen.getAllByText('Custom')
      expect(customLabels.length).toBe(2)
    })

    it('renders Create role button', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /create role/i })).toBeInTheDocument()
    })

    it('renders table column headers', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByRole('columnheader', { name: /Row expansion/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Name/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Description/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Type/i })).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('displays EmptyStateNoData when no roles and no filters', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: { resources: [], next: null, total: 0 },
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: mockRefetch,
      } as never)

      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByText('No roles yet')).toBeInTheDocument()
      expect(screen.getByText('No roles are available.')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Create role' })).not.toBeInTheDocument()
    })
  })

  describe('Loading and error states', () => {
    it('displays loading state when query is pending', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/projects') {
          return {
            data: [],
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: true,
          isError: false,
          error: null,
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    })

    it('displays error state when query fails', () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/projects') {
          return {
            data: [],
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isError: true,
          error: new Error('Failed to load roles'),
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    it('calls refetch when Retry is clicked on a retryable query error', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/projects') {
          return {
            data: [],
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isError: true,
          error: { message: 'Failed to load roles', retryable: true },
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      await user.click(screen.getByRole('button', { name: 'Retry' }))
      expect(mockRefetch).toHaveBeenCalledOnce()
    })
  })

  describe('Row actions', () => {
    it('shows kebab actions only for non-builtin roles', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      // There should be 2 kebab toggles (custom-editor and viewer), not 3
      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      expect(kebabs).toHaveLength(2)
    })

    it('opens edit dialog when edit action is clicked on a custom role', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const editOption = await screen.findByRole('menuitem', { name: /edit role/i })
      await user.click(editOption)

      await waitFor(() => {
        expect(screen.getByText('Edit custom-editor')).toBeInTheDocument()
      })
    })

    it('disables Edit role when user lacks update permission', async () => {
      mockUseRolePermissions.mockReturnValue({
        ...defaultRolePermissions,
        canUpdate: false,
        tooltips: {
          ...defaultRolePermissions.tooltips,
          update: 'You need permission to update roles.',
        },
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      expect(await screen.findByRole('menuitem', { name: /edit role/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Delete role when user lacks delete permission', async () => {
      mockUseRolePermissions.mockReturnValue({
        ...defaultRolePermissions,
        canDelete: false,
        tooltips: {
          ...defaultRolePermissions.tooltips,
          delete: 'You need permission to delete roles.',
        },
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      expect(await screen.findByRole('menuitem', { name: /delete role/i })).toHaveAttribute('aria-disabled', 'true')
    })

    it('opens delete confirmation when delete action is clicked', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /delete role/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete role?')).toBeInTheDocument()
      })
    })
  })

  describe('Delete flow', () => {
    async function openDeleteDialog() {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /delete role/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete role?')).toBeInTheDocument()
      })
      return user
    }

    it('shows role name in delete confirmation body', async () => {
      await openDeleteDialog()

      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText(/will be deleted/i)).toBeInTheDocument()
      expect(within(dialog).getByText('custom-editor')).toBeInTheDocument()
    })

    it('calls delete mutation when Delete button is clicked', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('checkbox'))
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      expect(mockDeleteMutate).toHaveBeenCalled()
      const callArgs = mockDeleteMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({ params: { path: { role_id: 'role-2' } } })
    })

    it('refetches roles and closes dialog on successful delete', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('checkbox'))
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onSuccess: () => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      expect(invalidateAuthzCaches).toHaveBeenCalledWith(queryClient)
      expect(mockRefetch).toHaveBeenCalled()
      await waitFor(() => {
        expect(screen.queryByText('Delete role?')).not.toBeInTheDocument()
      })
    })

    it('closes dialog on failed delete', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('checkbox'))
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      const callbacks = mockDeleteMutate.mock.calls[0][1] as {
        onError: (error: unknown) => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError(new Error('Server error'))
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Delete role?')).not.toBeInTheDocument()
      })
    })

    it('closes delete dialog when Cancel button is clicked', async () => {
      const user = await openDeleteDialog()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Delete role?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Create role dialog', () => {
    it('opens AddRoleDialog when Create role button is clicked', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      await user.click(screen.getByRole('button', { name: /create role/i }))

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Create role' })).toBeInTheDocument()
      })
    })
  })

  describe('Sorting', () => {
    async function expectSortAfterColumnClick(columnPattern: RegExp, expectedSort: string) {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const header = screen.getByRole('columnheader', { name: columnPattern })
      await user.click(within(header).getByRole('button'))

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', expectedSort)
      })
    }

    it('renders sortable Name column', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const nameHeader = screen.getByRole('columnheader', { name: /Name/i })
      expect(within(nameHeader).getByRole('button')).toBeInTheDocument()
    })

    it('renders sortable Type column', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const typeHeader = screen.getByRole('columnheader', { name: /Type/i })
      expect(within(typeHeader).getByRole('button')).toBeInTheDocument()
    })

    it('passes pagination params to the API', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const callArgs = vi
        .mocked(accessClient.useQuery)
        .mock.calls.find((call) => call[0] === 'get' && call[1] === '/roles')
      expect(callArgs).toBeDefined()
      const queryOptions = callArgs![2] as unknown as {
        params: { query: Record<string, unknown> }
      }
      expect(queryOptions.params.query).toMatchObject({
        limit: 20,
        include_total: true,
      })
    })

    it('sends ascending sort parameter when column is clicked', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const nameHeader = screen.getByRole('columnheader', { name: /Name/i })
      const sortButton = within(nameHeader).getByRole('button')

      await user.click(sortButton)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', 'name')
      })
    })

    it('sends descending sort parameter when column is clicked twice', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const nameHeader = screen.getByRole('columnheader', { name: /Name/i })
      const sortButton = within(nameHeader).getByRole('button')

      await user.click(sortButton)
      await user.click(sortButton)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('sort', '-name')
      })
    })

    it.each([
      { column: /Scope/i, sort: 'scope' },
      { column: /Project/i, sort: 'project_id' },
      { column: /Type/i, sort: 'is_builtin' },
    ])('sends $sort sort when column header is clicked', async ({ column, sort }) => {
      await expectSortAfterColumnClick(column, sort)
    })
  })

  describe('Pagination', () => {
    it('renders footer with item count', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })

    it('navigates to next page when next cursor is available', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
        if (path === '/projects') {
          return {
            data: [],
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: mockRefetch,
          } as never
        }
        return {
          data: { resources: mockRoles, next: 'next-cursor', total: 25 },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const nextButton = screen.getByRole('button', { name: /next page/i })
      await user.click(nextButton)

      // After clicking next, the cursor param should be sent
      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toHaveProperty('cursor', 'next-cursor')
      })
    })
  })

  describe('Filter bar', () => {
    it('does not offer Description in the attribute field selector', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const filterToolbar = screen.getByRole('search')
      expect(filterToolbar).toBeTruthy()
      await user.click(within(filterToolbar).getByRole('button', { name: /^Name$/ }))

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Scope' })).toBeInTheDocument()
      })
      expect(screen.queryByRole('option', { name: /^Description$/ })).not.toBeInTheDocument()
    })
  })

  describe('Expandable rows', () => {
    it('renders a dash when a role has no description', () => {
      render(<RolesTab />, { wrapper: createWrapper() })

      const viewerRow = screen.getByRole('row', { name: /viewer/i })
      expect(within(viewerRow).getAllByText('-').length).toBeGreaterThan(0)
    })

    it('policies are hidden by default and shown when row is expanded', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.queryByText('admin-policy')).not.toBeVisible()

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('admin-policy')).toBeVisible()
      expect(screen.getByText('read-all')).toBeVisible()
    })

    it('expand-all button expands all rows, clicking again collapses them', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const expandAllButton = screen.getByRole('button', { name: /expand all/i })
      await user.click(expandAllButton)

      expect(screen.getByText('admin-policy')).toBeVisible()
      expect(screen.getByText('workflow-edit')).toBeVisible()

      await user.click(screen.getByRole('button', { name: /expand all|collapse all/i }))

      expect(screen.queryByText('admin-policy')).not.toBeVisible()
      expect(screen.queryByText('workflow-edit')).not.toBeVisible()
    })

    it('collapses an expanded row when the details button is clicked again', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])
      expect(screen.getByText('admin-policy')).toBeVisible()

      await user.click(expandButtons[0])
      expect(screen.queryByText('admin-policy')).not.toBeVisible()
    })

    it('toggling a single row does not affect other rows', async () => {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const expandButtons = screen.getAllByRole('button', { name: /details/i })
      await user.click(expandButtons[0])

      expect(screen.getByText('admin-policy')).toBeVisible()
      expect(screen.queryByText('workflow-edit')).not.toBeVisible()
    })
  })

  describe('Delete dialog acknowledgement checkbox', () => {
    async function openDeleteDialog() {
      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const kebabs = screen.getAllByRole('button', { name: 'Kebab toggle' })
      await user.click(kebabs[0])

      const deleteOption = await screen.findByRole('menuitem', { name: /delete role/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete role?')).toBeInTheDocument()
      })
      return user
    }

    it('renders acknowledgement checkbox and role name in the delete dialog', async () => {
      await openDeleteDialog()

      const dialog = screen.getByRole('dialog')
      const checkbox = within(dialog).getByRole('checkbox', {
        name: 'I understand this role will be permanently deleted.',
      })
      expect(checkbox).toBeInTheDocument()
      expect(checkbox).not.toBeChecked()
      expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument()
    })

    it('disables Delete button until acknowledgement checkbox is checked', async () => {
      const user = await openDeleteDialog()

      expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()

      await user.click(
        screen.getByRole('checkbox', {
          name: 'I understand this role will be permanently deleted.',
        })
      )

      expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    })
  })

  describe('Create role permission gating', () => {
    it('disables Create role when user lacks create permission', () => {
      mockUseRolePermissions.mockReturnValue({
        canCreate: false,
        canUpdate: true,
        canDelete: true,
        isLoading: false,
        tooltips: {
          create: 'You need permission to create roles.',
          update: 'You need permission to update roles.',
          delete: 'You need permission to delete roles.',
        },
      })

      render(<RolesTab />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: 'Create role' })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('Filter empty state', () => {
    it('shows filter toolbar with Create role when filters are active but no results', async () => {
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasNameFilter = opts?.params?.query?.['name[contains]']
        return {
          data: { resources: hasNameFilter ? [] : mockRoles, next: null, total: hasNameFilter ? 0 : 3 },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Create role' })).toBeInTheDocument()
      })
    })

    it('shows filter empty state when filters are active but no results', async () => {
      // Mock implementation: return data on initial load, empty after filter
      vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
        const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
        const hasNameFilter = opts?.params?.query?.['name[contains]']
        return {
          data: { resources: hasNameFilter ? [] : mockRoles, next: null, total: hasNameFilter ? 0 : 3 },
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: mockRefetch,
        } as never
      })

      const user = userEvent.setup()
      render(<RolesTab />, { wrapper: createWrapper() })

      // Apply a filter by typing in the name filter input and pressing Enter
      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })
  })
})
