import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'
import { accessClient, accessFetchClient } from '../access/accessClient'
import { useSelectableProjects } from '../access/useAllProjects'

import { AssignRoleModal } from './AssignRoleModal'
import type { RolePrincipalType } from './RoleAssignmentTypes'

vi.mock('../access/accessClient', () => ({
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

vi.mock('../../hooks/useDebouncedValue', () => ({
  useDebouncedValue: <T,>(value: T) => value,
}))

vi.mock('../access/useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

const mockMutateAsync = vi.fn()

const mockMutationReturn = {
  mutate: vi.fn(),
  mutateAsync: mockMutateAsync,
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

const systemRoles = [
  { id: 'r1', name: 'admin-role', description: 'Admin', project_id: null, is_builtin: true, policies: [] },
  { id: 'r2', name: 'viewer-role', description: 'Viewer', project_id: null, is_builtin: true, policies: [] },
]

const projectBuiltinRoles = [
  { id: 'r3', name: 'project-admin', description: 'Project Admin', project_id: null, is_builtin: true, policies: [] },
  { id: 'r4', name: 'project-user', description: 'Project User', project_id: null, is_builtin: true, policies: [] },
  {
    id: 'r5',
    name: 'project-auditor',
    description: 'Project Auditor',
    project_id: null,
    is_builtin: true,
    policies: [],
  },
]

const mockProjects = [
  {
    id: 'proj1',
    name: 'Project Alpha',
    description: undefined,
    labels: {},
    is_default: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
  {
    id: 'proj2',
    name: 'Project Beta',
    description: undefined,
    labels: {},
    is_default: false,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-02T00:00:00Z',
  },
]

describe('AssignRoleModal', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  function setupMocks() {
    vi.mocked(useSelectableProjects).mockReturnValue({
      projects: mockProjects,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(accessClient.useQuery).mockImplementation(
      (_method: string, path: string, options?: { params?: { query?: { scope?: string; is_builtin?: boolean } } }) => {
        if (path === '/roles') {
          const query = options?.params?.query
          let roles = systemRoles
          if (query?.scope === 'project') {
            roles = projectBuiltinRoles
          }
          return {
            data: { resources: roles, next: null },
            isPending: false,
            isError: false,
            error: null,
            isFetching: false,
            refetch: vi.fn(),
          } as never
        }
        return {
          data: undefined,
          isPending: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
    )

    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    setupMocks()
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: [], next: null },
      error: undefined,
    } as never)
  })

  async function renderModal(
    props: Partial<{
      principalType: RolePrincipalType
      principalId: string
      isOpen: boolean
    }> = {}
  ) {
    const view = render(
      <AssignRoleModal
        principalType={props.principalType ?? 'user'}
        principalId={props.principalId ?? 'u1'}
        isOpen={props.isOpen ?? true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )
    await act(async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 0)
      })
    })
    return view
  }

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      let results: Awaited<ReturnType<typeof axe>>
      const { container } = await renderModal()
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders modal with "Assign roles" title', async () => {
      await renderModal()
      expect(screen.getByText('Assign roles')).toBeInTheDocument()
    })

    it('renders Scope, Roles form groups', async () => {
      await renderModal()
      expect(screen.getByText('Scope')).toBeInTheDocument()
      expect(screen.getByText('Roles')).toBeInTheDocument()
    })

    it('renders Assign and Cancel buttons', async () => {
      await renderModal()
      expect(screen.getByRole('button', { name: /Assign/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('defaults to System scope', async () => {
      await renderModal()
      // The SingleSelect toggle shows "System" by default
      expect(screen.getByText('System')).toBeInTheDocument()
    })

    it('does not render Project selector by default (system scope)', async () => {
      await renderModal()
      expect(screen.queryByText('Project')).not.toBeInTheDocument()
    })

    it('does not render when isOpen is false', async () => {
      await renderModal({ isOpen: false })
      expect(screen.queryByText('Assign roles')).not.toBeInTheDocument()
    })
  })

  describe('Scope switching', () => {
    it('shows Project selector when scope is changed to Project', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Click the scope toggle to open the select
      const scopeToggle = screen.getByRole('button', { name: 'System' })
      await user.click(scopeToggle)

      // Select "Project"
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Project form group should appear - use the project placeholder as proof
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })
    })

    it('clears selected roles when scope changes', async () => {
      const user = userEvent.setup()
      await renderModal()

      // First, select a role in system scope — click the typeahead input to open
      const roleInput = screen.getByPlaceholderText('Search for roles...')
      await user.click(roleInput)

      // Select admin-role
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      // The Assign button should now show count
      expect(screen.getByRole('button', { name: /Assign \(1\)/i })).toBeInTheDocument()

      // Switch scope to Project
      await user.click(screen.getByRole('button', { name: 'System' }))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // After scope change, selected roles should be cleared — button text goes back to just "Assign"
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Assign\s*$/i })).toBeInTheDocument()
      })
    })
  })

  describe('Role filtering by scope', () => {
    it('shows only system roles (project_id === null) in system scope', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Open the role selector
      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))

      // System roles: admin-role, viewer-role (project_id === null)
      expect(screen.getByRole('option', { name: /admin-role/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /viewer-role/i })).toBeInTheDocument()
      // project-editor has project_id !== null, should not appear
      expect(screen.queryByRole('option', { name: /project-editor/i })).not.toBeInTheDocument()
    })

    it('shows only project-scoped built-in roles in project scope', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Switch to project scope
      const scopeToggle = screen.getByText('System')
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Wait for project selector to appear
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })

      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))

      // Only project-* roles (project_id === null && name.startsWith('project-'))
      expect(screen.getByRole('option', { name: /project-admin/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /project-user/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /project-auditor/i })).toBeInTheDocument()
      // System-only roles should not appear
      expect(screen.queryByRole('option', { name: /^admin-role/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /^viewer-role/i })).not.toBeInTheDocument()
    })
  })

  describe('Submit button state', () => {
    it('stays enabled when no roles are selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      const submitButton = screen.getByRole('button', { name: /Assign/i })
      expect(submitButton).toBeEnabled()
      await user.click(submitButton)
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('shows role count in button when roles are selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Select a role
      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      expect(screen.getByRole('button', { name: /Assign \(1\)/i })).toBeInTheDocument()
    })
  })

  describe('Validation errors', () => {
    it('shows inline error when Assign is clicked with no roles selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      await user.click(screen.getByRole('button', { name: /Assign/i }))

      await waitFor(() => {
        expect(screen.getByText('Select at least one role')).toBeInTheDocument()
      })
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('shows inline error when project scope has roles but no project selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      await user.click(screen.getByRole('button', { name: 'System' }))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })

      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /project-admin/i }))

      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(screen.getByText('Project is required')).toBeInTheDocument()
      })
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('clears role error when a role is selected after failed submit', async () => {
      const user = userEvent.setup()
      await renderModal()

      await user.click(screen.getByRole('button', { name: /Assign/i }))

      await waitFor(() => {
        expect(screen.getByText('Select at least one role')).toBeInTheDocument()
      })

      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      await waitFor(() => {
        expect(screen.queryByText('Select at least one role')).not.toBeInTheDocument()
      })
    })
  })

  describe('Form submission', () => {
    it('assigns user role on submit', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'user', principalId: 'u1' })

      // Select a role
      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      // Submit
      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          body: { principal_id: 'u1', role_name: 'admin-role' },
        })
      })

      // Should call onSuccess and onClose
      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalled()
        expect(mockOnClose).toHaveBeenCalled()
      })
    })

    it('assigns system group role on submit', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'group', principalId: 'g1' })

      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          body: { group_id: 'g1', role_name: 'admin-role' },
        })
      })
    })

    it('assigns project user role on submit', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'user', principalId: 'u1' })

      // Switch to project scope
      await user.click(screen.getByText('System'))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Wait for project selector
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })

      // Open project selector
      const projectToggle = screen.getByRole('button', { name: 'Select a project...' })
      await user.click(projectToggle)
      await user.click(screen.getByRole('option', { name: 'Project Alpha' }))

      // Select a role (in project scope, id = name for project-* roles)
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /project-admin/i }))

      // Submit
      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          params: { path: { project_id: 'proj1' } },
          body: { principal_id: 'u1', role_name: 'project-admin' },
        })
      })
    })

    it('assigns project group role on submit', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'group', principalId: 'g1' })

      // Switch to project scope
      await user.click(screen.getByText('System'))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Wait for project selector
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })
      const projectToggle = screen.getByRole('button', { name: 'Select a project...' })
      await user.click(projectToggle)
      await user.click(screen.getByRole('option', { name: 'Project Alpha' }))

      // Select a role (project-scoped roles)
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /project-admin/i }))

      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          params: { path: { project_id: 'proj1' } },
          body: { group_id: 'g1', role_name: 'project-admin' },
        })
      })
    })

    it('does not submit when no roles are selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      const submitButton = screen.getByRole('button', { name: /Assign/i })
      expect(submitButton).toBeEnabled()

      await user.click(submitButton)
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('does not submit in project scope without a project selected', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Switch to project scope
      await user.click(screen.getByText('System'))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Wait for project selector to appear
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
      })

      // Select a role (without selecting a project first)
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /project-admin/i }))

      const submitButton = screen.getByRole('button', { name: /Assign \(1\)/i })
      expect(submitButton).toBeEnabled()
      await user.click(submitButton)
      expect(mockMutateAsync).not.toHaveBeenCalled()
    })

    it('shows success alert with count for single role assignment', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'user', principalId: 'u1' })

      // Select a role
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      // Submit
      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      // Should show singular success alert
      await waitFor(() => {
        expect(screen.getByText('Role assigned')).toBeInTheDocument()
      })
    })
  })

  describe('Error handling', () => {
    it('shows error alert when assignment fails', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockRejectedValue(new Error('Server error'))

      await renderModal({ principalType: 'user', principalId: 'u1' })

      // Select a role
      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      // Submit
      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      // The alert should appear via AlertProvider
      await waitFor(() => {
        expect(screen.getByText('Failed to assign roles')).toBeInTheDocument()
      })

      // onSuccess and onClose are NOT called when all assignments fail
      expect(mockOnSuccess).not.toHaveBeenCalled()
      expect(mockOnClose).not.toHaveBeenCalled()
    })
  })

  describe('Cancel and close', () => {
    it('resets state and calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup()
      await renderModal()

      // Select a role first
      // Open the role multi-select via its placeholder/input
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /admin-role/i }))

      // Click Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Service account principal type', () => {
    it('defaults to project scope for service_account', async () => {
      await renderModal({ principalType: 'service_account', principalId: 'sa-1' })

      // Project selector should be visible (scope defaults to 'project')
      expect(screen.getByRole('button', { name: 'Select a project...' })).toBeInTheDocument()
    })

    it('hides scope selector for service_account', async () => {
      await renderModal({ principalType: 'service_account', principalId: 'sa-1' })

      // Scope form group should not be present
      expect(screen.queryByText('Scope')).not.toBeInTheDocument()
    })

    it('assigns project SA role on submit', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockResolvedValue({})

      await renderModal({ principalType: 'service_account', principalId: 'sa-1' })

      // Select a project
      const projectToggle = screen.getByRole('button', { name: 'Select a project...' })
      await user.click(projectToggle)
      await user.click(screen.getByRole('option', { name: 'Project Alpha' }))

      // Select a role (project-scoped roles shown by default)
      await user.click(screen.getByPlaceholderText('Search for roles...'))
      await user.click(screen.getByRole('option', { name: /project-admin/i }))

      // Submit
      await user.click(screen.getByRole('button', { name: /Assign \(1\)/i }))

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          params: { path: { project_id: 'proj1' } },
          body: { principal_id: 'sa-1', role_name: 'project-admin' },
        })
      })
    })
  })

  describe('Already-assigned role filtering', () => {
    it('filters out already-assigned system roles from dropdown', async () => {
      const user = userEvent.setup()

      vi.mocked(accessFetchClient.GET).mockResolvedValue({
        data: {
          resources: [{ role_name: 'admin-role', project_id: null }],
          next: null,
        },
        error: undefined,
      } as never)

      await renderModal({ principalType: 'user', principalId: 'user-1' })

      // Open role dropdown
      await user.click(screen.getByPlaceholderText('Search for roles...'))

      // admin-role should not appear (already assigned at system scope)
      await waitFor(() => {
        expect(screen.queryByRole('option', { name: /admin-role/i })).not.toBeInTheDocument()
      })

      // Other roles should still appear
      expect(screen.getByRole('option', { name: /viewer-role/i })).toBeInTheDocument()
    })

    it('filters out already-assigned project roles for selected project', async () => {
      const user = userEvent.setup()

      vi.mocked(accessFetchClient.GET).mockResolvedValue({
        data: {
          resources: [{ role_name: 'project-admin', project_id: 'proj1' }],
          next: null,
        },
        error: undefined,
      } as never)

      await renderModal({ principalType: 'user', principalId: 'user-1' })

      // Switch to project scope
      const scopeToggle = screen.getByRole('button', { name: 'System' })
      await user.click(scopeToggle)
      await user.click(screen.getByRole('option', { name: 'Project' }))

      // Select project
      const projectToggle = screen.getByRole('button', { name: 'Select a project...' })
      await user.click(projectToggle)
      await user.click(screen.getByRole('option', { name: 'Project Alpha' }))

      // Open role dropdown
      await user.click(screen.getByPlaceholderText('Search for roles...'))

      // project-admin should not appear for proj1 (already assigned)
      await waitFor(() => {
        expect(screen.queryByRole('option', { name: /project-admin/i })).not.toBeInTheDocument()
      })

      // Other project roles should appear
      expect(screen.getByRole('option', { name: /project-auditor/i })).toBeInTheDocument()
    })

    it('shows warning when assignments request fails', async () => {
      vi.mocked(accessFetchClient.GET).mockResolvedValue({
        data: undefined,
        error: { detail: 'Server error' },
      } as never)

      await renderModal({ principalType: 'user', principalId: 'user-1' })

      await waitFor(() => {
        expect(screen.getByText('Unable to check existing assignments')).toBeInTheDocument()
      })
    })

    it('shows all roles when no assignments exist', async () => {
      const user = userEvent.setup()

      await renderModal({ principalType: 'user', principalId: 'user-1' })

      // Open role dropdown
      await user.click(screen.getByPlaceholderText('Search for roles...'))

      // All roles should appear (no filtering)
      expect(screen.getByRole('option', { name: /admin-role/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /viewer-role/i })).toBeInTheDocument()
    })
  })
})
