import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { PRINCIPAL_TYPE_HELP, ROLE_HELP, SCOPE_HELP } from './accessControlFieldHelpText'
import { AssignRoleDialog } from './AssignRoleDialog'
import { useSelectableProjects } from './useAllProjects'

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    GET: vi.fn(),
    use: vi.fn(),
  },
}))

vi.mock('../../hooks/useDebouncedValue', () => ({
  useDebouncedValue: <T,>(value: T) => value,
}))

vi.mock('./useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

// ── Test data ────────────────────────────────────────────────────────────────

const mockProjects = [
  {
    id: 'p1',
    name: 'Project Alpha',
    description: undefined,
    labels: {},
    is_default: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'Project Beta',
    description: undefined,
    labels: {},
    is_default: false,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-02T00:00:00Z',
  },
]

const mockSystemRoles = [
  {
    id: 'r1',
    name: 'Admin',
    description: null,
    policies: [],
    is_builtin: true,
    is_system_scoped: true,
    project_id: null,
    labels: {},
    created_at: null,
    updated_at: null,
  },
  {
    id: 'r2',
    name: 'Viewer',
    description: null,
    policies: [],
    is_builtin: true,
    is_system_scoped: true,
    project_id: null,
    labels: {},
    created_at: null,
    updated_at: null,
  },
]

const mockProjectRoles = [
  {
    id: 'r3',
    name: 'ProjectAdmin',
    description: null,
    policies: [],
    is_builtin: true,
    is_system_scoped: false,
    project_id: 'p1',
    labels: {},
    created_at: null,
    updated_at: null,
  },
]

const mockMutationReturn = {
  mutate: vi.fn(),
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
  status: 'idle' as const,
  isPaused: false,
}

const defaultQueryReturn = {
  data: undefined,
  isPending: false,
  isError: false,
  error: null,
  isFetching: false,
  refetch: vi.fn(),
}

function setupDefaultMocks() {
  vi.mocked(useSelectableProjects).mockReturnValue({
    projects: mockProjects,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })

  vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/roles') {
      return {
        ...defaultQueryReturn,
        data: { resources: mockSystemRoles, next: null },
      } as never
    }
    if (path === '/projects/{project_id}/roles') {
      return {
        ...defaultQueryReturn,
        data: { resources: mockProjectRoles, next: null },
      } as never
    }
    if (path === '/users/directory') {
      return {
        ...defaultQueryReturn,
        data: {
          resources: [
            { id: 'u1', username: 'alice', email: 'alice@test.com', first_name: 'Alice' },
            { id: 'u2', username: 'bob', email: 'bob@test.com', first_name: 'Bob' },
          ],
          next: null,
        },
      } as never
    }
    if (path === '/groups/directory') {
      return {
        ...defaultQueryReturn,
        data: {
          resources: [
            { id: 'g1', name: 'test-group' },
            { id: 'g2', name: 'another-group' },
          ],
          next: null,
        },
      } as never
    }
    if (path === '/service_accounts') {
      return {
        ...defaultQueryReturn,
        data: {
          resources: [
            { id: 'sa-1', name: 'my-service-account' },
            { id: 'sa-2', name: 'another-sa' },
          ],
          next: null,
        },
      } as never
    }
    return { ...defaultQueryReturn } as never
  })
  vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn as never)
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('AssignRoleDialog', () => {
  const defaultProps = {
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    setupDefaultMocks()
  })

  describe('Rendering', () => {
    it('renders the dialog with title', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Add Assignment')).toBeInTheDocument()
    })

    it('renders principal type and scope selectors with default values', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const principalOrGroupSelect = screen.getByLabelText('Principal type')
      expect(principalOrGroupSelect).toBeInTheDocument()

      const scopeSelect = screen.getByLabelText('Scope')
      expect(scopeSelect).toBeInTheDocument()
    })

    it('renders Add and Cancel buttons', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      expect(screen.getByRole('button', { name: 'Add assignment' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders User field for user-project type (default)', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      expect(screen.getByPlaceholderText('Select a user...')).toBeInTheDocument()
    })

    it('renders Project field for project-scoped type', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Project field is rendered for user-project (default) -- check for the typeahead placeholder
      expect(screen.getByPlaceholderText('Select a project...')).toBeInTheDocument()
    })

    it('renders Role field', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Role')).toBeInTheDocument()
    })
  })

  describe('Principal Type and Scope Switching', () => {
    it('shows Group field when principal type is changed to group', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Group' }))

      expect(screen.getByPlaceholderText('Select a group...')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Select a user...')).not.toBeInTheDocument()
    })

    it('shows User field for user principal type with system scope', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      expect(screen.getByPlaceholderText('Select a user...')).toBeInTheDocument()
      // No project field for system-scoped
      expect(screen.queryByPlaceholderText('Select a project...')).not.toBeInTheDocument()
    })

    it('shows Group field for group principal type with system scope', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Group' }))

      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      expect(screen.getByPlaceholderText('Select a group...')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Select a project...')).not.toBeInTheDocument()
    })
  })

  describe('Search Filtering', () => {
    it('passes search filter params when typing in typeahead fields', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const userInput = screen.getByPlaceholderText('Select a user...')
      await user.type(userInput, 'ali')

      await waitFor(() => {
        expect(accessClient.useQuery).toHaveBeenCalledWith('get', '/users/directory', {
          params: { query: { sort: 'username', limit: 20, 'username[contains]': 'ali' } },
        })
      })
    })

    it('passes search filter for groups when typing', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch to group principal type
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Group' }))

      const groupInput = screen.getByPlaceholderText('Select a group...')
      await user.type(groupInput, 'test')

      await waitFor(() => {
        expect(accessClient.useQuery).toHaveBeenCalledWith('get', '/groups/directory', {
          params: { query: { sort: 'name', limit: 20, 'name[contains]': 'test' } },
        })
      })
    })

    it('passes search filter for roles when typing', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch to system scope so role field is immediately available
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.type(roleInput, 'adm')

      await waitFor(() => {
        expect(accessClient.useQuery).toHaveBeenCalledWith('get', '/roles', {
          params: { query: { sort: 'name', limit: 20, scope: 'system', 'name[contains]': 'adm' } },
        })
      })
    })

    it('passes search filter for service accounts when typing', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch to service account principal type
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Service Account' }))

      const saInput = screen.getByPlaceholderText('Select a service account...')
      await user.type(saInput, 'my-sa')

      await waitFor(() => {
        expect(accessClient.useQuery).toHaveBeenCalledWith(
          'get',
          '/service_accounts',
          { params: { query: { sort: 'name', limit: 20, name: 'my-sa' } } },
          { enabled: true }
        )
      })
    })
  })

  describe('Form Submission', () => {
    const findOptionTimeout = { timeout: 15_000 }

    async function fillAndSubmitUserProjectForm(user: ReturnType<typeof userEvent.setup>) {
      // Select a project from the typeahead FIRST (role dropdown is disabled until project is selected)
      const projectInput = screen.getByPlaceholderText('Select a project...')
      await user.click(projectInput)
      const projectOption = await screen.findByRole('option', { name: 'Project Alpha' }, findOptionTimeout)
      await user.click(projectOption)

      // Select a user from the typeahead
      const userInput = screen.getByPlaceholderText('Select a user...')
      await user.click(userInput)
      const userOption = await screen.findByRole('option', { name: 'alice' }, findOptionTimeout)
      await user.click(userOption)

      // Select a role from the typeahead (options include scope tags, e.g. "Project ProjectAdmin")
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: /ProjectAdmin/ }, findOptionTimeout)
      await user.click(roleOption)

      // Submit
      await user.click(screen.getByRole('button', { name: 'Add assignment' }))
    }

    it('calls assignProjectRole mutation for user-project type', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      await fillAndSubmitUserProjectForm(user)

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })
    })

    it('calls assignProjectGroupRole mutation for group-project type', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch principal type to group
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Group' }))

      // Select a project FIRST (role dropdown is disabled until project is selected)
      const projectInput = screen.getByPlaceholderText('Select a project...')
      await user.click(projectInput)
      const projectOption = await screen.findByRole('option', { name: 'Project Alpha' })
      await user.click(projectOption)

      // Select a group from the typeahead
      const groupInput = screen.getByPlaceholderText('Select a group...')
      await user.click(groupInput)
      const groupOption = await screen.findByRole('option', { name: 'test-group' })
      await user.click(groupOption)

      // Select a role (options include scope tags)
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: /ProjectAdmin/ })
      await user.click(roleOption)

      await user.click(screen.getByRole('button', { name: 'Add assignment' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })
    })

    it('calls onSuccess and onClose on successful mutation', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()
      const user = userEvent.setup()
      render(<AssignRoleDialog onClose={onClose} onSuccess={onSuccess} />, { wrapper })

      await fillAndSubmitUserProjectForm(user)

      await waitFor(
        () => {
          expect(mockMutate).toHaveBeenCalled()
        },
        { timeout: 15_000 }
      )

      // Simulate successful mutation callback
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onSuccess?: () => void } | undefined
      if (callbacks?.onSuccess) {
        act(() => {
          callbacks.onSuccess!()
        })
        expect(onSuccess).toHaveBeenCalled()
        expect(onClose).toHaveBeenCalled()
      }
    }, 25_000)

    it('handles error mutation callback', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      await fillAndSubmitUserProjectForm(user)

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Simulate error mutation callback
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onError?: (err: Error) => void } | undefined
      if (callbacks?.onError) {
        act(() => {
          callbacks.onError!(new Error('Permission denied'))
        })
      }
    })

    it('calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<AssignRoleDialog {...defaultProps} onClose={onClose} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('System-Scoped Submission', () => {
    it('calls assignSystemUserRole mutation for user-system type', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch scope to system
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      // Select a user from the typeahead
      const userInput = screen.getByPlaceholderText('Select a user...')
      await user.click(userInput)
      const userOption = await screen.findByRole('option', { name: 'alice' })
      await user.click(userOption)

      // Select a role (system-scoped uses role name as value)
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      // Use exact name to avoid matching "Project ProjectAdmin"
      const roleOption = await screen.findByRole('option', { name: 'Admin' })
      await user.click(roleOption)

      await user.click(screen.getByRole('button', { name: 'Add assignment' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: { principal_id: string; role_name: string } }]
      expect(callArgs[0]).toEqual({ body: { principal_id: 'u1', role_name: 'Admin' } })
    })

    it('calls assignSystemGroupRole mutation for group-system type', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch principal type to group
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Group' }))

      // Switch scope to system
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      // Select a group from the typeahead
      const groupInput = screen.getByPlaceholderText('Select a group...')
      await user.click(groupInput)
      const groupOption = await screen.findByRole('option', { name: 'test-group' })
      await user.click(groupOption)

      // Select a role
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: /Viewer/ })
      await user.click(roleOption)

      await user.click(screen.getByRole('button', { name: 'Add assignment' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: { group_id: string; role_name: string } }]
      expect(callArgs[0]).toEqual({
        body: { group_id: 'g1', role_name: 'Viewer' },
      })
    })
  })

  describe('Role Reset on Scope Switch', () => {
    it('clears role selection when switching from project to system scope', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Select a project first so the role dropdown becomes enabled
      const projectInput = screen.getByPlaceholderText('Select a project...')
      await user.click(projectInput)
      await user.click(await screen.findByRole('option', { name: 'Project Alpha' }))

      // Select a role in project scope (default: user + project scope)
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: /ProjectAdmin/ })
      await user.click(roleOption)

      // Verify role is selected (clear buttons visible for both project and role)
      const clearButtons = screen.getAllByRole('button', { name: 'Clear selection' })
      expect(clearButtons.length).toBeGreaterThanOrEqual(1)

      // Switch scope to system (project field disappears, role resets)
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      // Role field should be cleared -- no clear button for role
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
      })
    })

    it('clears role selection when switching from system to project scope', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch scope to system first
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      // Select a role in system scope (use exact name to avoid multiple matches)
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: 'Admin' })
      await user.click(roleOption)

      // Verify role is selected
      expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()

      // Switch back to project scope
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Role field should be cleared
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
      })
    })

    it('submits correct role value after switching to system scope and re-selecting', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Select a project first so the role dropdown becomes enabled
      const projectInput = screen.getByPlaceholderText('Select a project...')
      await user.click(projectInput)
      await user.click(await screen.findByRole('option', { name: 'Project Alpha' }))

      // Select a role in project scope
      let roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      let roleOption = await screen.findByRole('option', { name: /ProjectAdmin/ })
      await user.click(roleOption)

      // Switch scope to system
      const scopeToggle = screen.getByRole('button', { name: 'Scope' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'System' }))

      // Select a user from the typeahead
      const userInput = screen.getByPlaceholderText('Select a user...')
      await user.click(userInput)
      const userOption = await screen.findByRole('option', { name: 'bob' })
      await user.click(userOption)

      // Re-select a role (now uses system roles)
      roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      roleOption = await screen.findByRole('option', { name: /Viewer/ })
      await user.click(roleOption)

      await user.click(screen.getByRole('button', { name: 'Add assignment' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: { principal_id: string; role_name: string } }]
      expect(callArgs[0]).toEqual({ body: { principal_id: 'u2', role_name: 'Viewer' } })
    })
  })

  describe('Project ID Default', () => {
    it('renders without error', () => {
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Add Assignment')).toBeInTheDocument()
    })
  })

  describe('Service Account Principal Type', () => {
    it('shows Service Account field when principal type changed to service_account', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Service Account' }))

      expect(screen.getByPlaceholderText('Select a service account...')).toBeInTheDocument()
    })

    it('hides User and Group fields when Service Account is selected', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Service Account' }))

      expect(screen.queryByPlaceholderText('Select a user...')).not.toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Select a group...')).not.toBeInTheDocument()
    })

    it('hides Scope field but shows Project field when Service Account is selected', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch principal type to service_account
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Service Account' }))

      expect(screen.queryByLabelText('Scope')).not.toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select a project...')).toBeInTheDocument()
    })

    it('calls project role mutation with service_account principal type', async () => {
      const mockMutate = vi.fn()
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutate: mockMutate,
      } as never)

      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      // Switch principal type to service_account
      const principalToggle = screen.getByRole('button', { name: 'Principal type' })
      await user.click(principalToggle)
      await user.click(screen.getByRole('option', { name: 'Service Account' }))

      // Select a project first
      const projectInput = screen.getByPlaceholderText('Select a project...')
      await user.click(projectInput)
      const projectOption = await screen.findByRole('option', { name: 'Project Alpha' })
      await user.click(projectOption)

      // Select a service account
      const saInput = screen.getByPlaceholderText('Select a service account...')
      await user.click(saInput)
      const saOption = await screen.findByRole('option', { name: 'my-service-account' })
      await user.click(saOption)

      // Select a role (project roles since scope is forced to project)
      const roleInput = screen.getByPlaceholderText('Select a role...')
      await user.click(roleInput)
      const roleOption = await screen.findByRole('option', { name: /ProjectAdmin/ })
      await user.click(roleOption)

      await user.click(screen.getByRole('button', { name: 'Add assignment' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [
        {
          params: { path: { project_id: string } }
          body: { principal_id: string; role_name: string }
        },
      ]
      expect(callArgs[0].body).toEqual({
        principal_id: 'sa-1',
        role_name: 'ProjectAdmin',
      })
    })
  })

  describe('field help popovers', () => {
    it('shows principal type, scope, and role help on click', async () => {
      const user = userEvent.setup()
      render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'More info for Principal type' }))
      expect(screen.getByText(PRINCIPAL_TYPE_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Scope' }))
      expect(screen.getByText(SCOPE_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Role' }))
      expect(screen.getByText(ROLE_HELP)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<AssignRoleDialog {...defaultProps} />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
