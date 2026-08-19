import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { ROLE_HELP, SCOPE_HELP } from './accessControlFieldHelpText'
import { EditAssignmentDialog } from './EditAssignmentDialog'
import type { PermissionRow } from './types'
import { useAllRoles } from './useAllRoles'

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

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./useAllRoles', () => ({
  useAllRoles: vi.fn(),
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

const mockRoles = {
  resources: [
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
    {
      id: 'r3',
      name: 'Editor',
      description: null,
      policies: [],
      is_builtin: true,
      is_system_scoped: false,
      project_id: null,
      labels: {},
      created_at: null,
      updated_at: null,
    },
  ],
}

const projectRow: PermissionRow = {
  id: 'pr1',
  principalType: 'user',
  principalId: 'u1',
  principalName: 'alice',
  assignmentType: 'role',
  assignmentName: 'Admin',
  scopeType: 'project',
  scopeName: 'Project Alpha',
  projectId: 'p1',
  roleDescription: null,
  rolePolicies: [],
  sourceEndpoint: 'project-role-assignments',
}

const projectGroupRow: PermissionRow = {
  id: 'pgr1',
  principalType: 'group',
  principalId: 'g1',
  principalName: 'Devs',
  assignmentType: 'role',
  assignmentName: 'Editor',
  scopeType: 'project',
  scopeName: 'Project Alpha',
  projectId: 'p1',
  roleDescription: null,
  rolePolicies: [],
  sourceEndpoint: 'project-role-assignments',
}

const systemUserRow: PermissionRow = {
  id: 'sur1',
  principalType: 'user',
  principalId: 'u2',
  principalName: 'bob',
  assignmentType: 'role',
  assignmentName: 'Viewer',
  scopeType: 'system',
  scopeName: 'System',
  roleDescription: null,
  rolePolicies: [],
  sourceEndpoint: 'role-assignments',
  roleId: 'r2',
}

const systemGroupRow: PermissionRow = {
  id: 'sgr1',
  principalType: 'group',
  principalId: 'g2',
  principalName: 'Ops',
  assignmentType: 'role',
  assignmentName: 'Admin',
  scopeType: 'system',
  scopeName: 'System',
  roleDescription: null,
  rolePolicies: [],
  sourceEndpoint: 'role-assignments',
  roleId: 'r1',
}

const mockMutationReturn = {
  mutate: vi.fn(),
  mutateAsync: vi.fn().mockResolvedValue({ id: 'default-new-assignment-id' }),
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

function setupDefaultMocks() {
  vi.mocked(useAllRoles).mockReturnValue({
    roles: mockRoles.resources,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })

  vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn as never)
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('EditAssignmentDialog', () => {
  const defaultProps = {
    row: projectRow,
    displayName: 'alice',
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    setupDefaultMocks()
  })

  describe('Rendering', () => {
    it('renders the dialog with title', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Edit principal assignment')).toBeInTheDocument()
    })

    it('displays the principal name', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('alice')).toBeInTheDocument()
    })

    it('displays project scope name for project-scoped row', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    it('displays System for system-scoped row', () => {
      render(<EditAssignmentDialog {...defaultProps} row={systemUserRow} displayName="bob" />, { wrapper })

      expect(screen.getByText('System')).toBeInTheDocument()
    })

    it('renders Save and Cancel buttons', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders Role field', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Role')).toBeInTheDocument()
    })

    it('renders Principal label', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Principal')).toBeInTheDocument()
    })

    it('renders Scope label', () => {
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      expect(screen.getByText('Scope')).toBeInTheDocument()
    })

    it('shows scope and role help on click', async () => {
      const user = userEvent.setup()
      render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'More info for Scope' }))
      expect(screen.getByText(SCOPE_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Role' }))
      expect(screen.getByText(ROLE_HELP)).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('calls onClose when role has not changed', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<EditAssignmentDialog {...defaultProps} onClose={onClose} />, { wrapper })

      // Submit without changing the role
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled()
      })
    })

    it('calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<EditAssignmentDialog {...defaultProps} onClose={onClose} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onClose).toHaveBeenCalled()
    })

    it('executes assign-then-delete for project-roles when role changes', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({ id: 'new-assignment' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={projectRow} displayName="alice" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      // Open the role typeahead and select a different role
      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      // Select Viewer (different from current Admin)
      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      // Submit
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        // mutateAsync should be called (delete old, create new)
        expect(mutateAsyncSpy).toHaveBeenCalled()
      })
    })

    it('executes delete-then-create for project-group-roles when role changes', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({})
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()

      const user = userEvent.setup()
      render(
        <EditAssignmentDialog row={projectGroupRow} displayName="Devs" onClose={onClose} onSuccess={onSuccess} />,
        { wrapper }
      )

      // Open the role typeahead and select a different role
      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalled()
      })
    })

    it('executes assign-then-delete for user-role-assignments when role changes', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({ id: 'new-assignment' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onClose = vi.fn()
      const onSuccess = vi.fn()

      const user = userEvent.setup()
      render(<EditAssignmentDialog row={systemUserRow} displayName="bob" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      // System-scoped uses role.id as value, not role.name — default is empty
      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      const adminOption = await screen.findByRole('option', { name: 'Admin' })
      await user.click(adminOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalled()
      })
    })

    it('executes assign-then-delete for group-role-assignments when role changes', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({ id: 'new-assignment' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onClose = vi.fn()
      const onSuccess = vi.fn()

      const user = userEvent.setup()
      render(<EditAssignmentDialog row={systemGroupRow} displayName="Ops" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalled()
      })
    })

    it('calls onSuccess and onClose on successful update', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({ id: 'new-assignment' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()

      const user = userEvent.setup()
      render(<EditAssignmentDialog row={projectRow} displayName="alice" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled()
        expect(onClose).toHaveBeenCalled()
      })
    })

    it('invalidates role-assignments and authz caches on successful update', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValue({ id: 'new-assignment' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined)
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={projectRow} displayName="alice" onClose={vi.fn()} onSuccess={vi.fn()} />, {
        wrapper,
      })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      await user.click(await screen.findByRole('option', { name: 'Viewer' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['role-assignments'] })
      })
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['authz', 'can_i'] })
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['all-permissions'] })

      invalidateSpy.mockRestore()
    })
  })

  describe('Different Source Endpoints', () => {
    it('renders for project-group-roles endpoint', () => {
      render(<EditAssignmentDialog {...defaultProps} row={projectGroupRow} displayName="Devs" />, { wrapper })

      expect(screen.getByText('Devs')).toBeInTheDocument()
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    it('renders for user-role-assignments endpoint', () => {
      render(<EditAssignmentDialog {...defaultProps} row={systemUserRow} displayName="bob" />, { wrapper })

      expect(screen.getByText('bob')).toBeInTheDocument()
      expect(screen.getByText('System')).toBeInTheDocument()
    })

    it('renders for group-role-assignments endpoint', () => {
      render(<EditAssignmentDialog {...defaultProps} row={systemGroupRow} displayName="Ops" />, { wrapper })

      expect(screen.getByText('Ops')).toBeInTheDocument()
      expect(screen.getByText('System')).toBeInTheDocument()
    })
  })

  describe('Invalid row data', () => {
    it('shows error when project user assignment is missing projectId', async () => {
      const user = userEvent.setup()
      const rowMissingProject: PermissionRow = { ...projectRow, projectId: undefined }
      render(<EditAssignmentDialog {...defaultProps} row={rowMissingProject} />, { wrapper })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      await user.click(await screen.findByRole('option', { name: 'Viewer' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText('Invalid assignment: missing project ID')).toBeInTheDocument()
      })
    })

    it('shows error when project group assignment is missing projectId', async () => {
      const user = userEvent.setup()
      const rowMissingProject: PermissionRow = { ...projectGroupRow, projectId: undefined }
      render(<EditAssignmentDialog {...defaultProps} row={rowMissingProject} displayName="Devs" />, { wrapper })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      await user.click(await screen.findByRole('option', { name: 'Viewer' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText('Invalid assignment: missing project ID')).toBeInTheDocument()
      })
    })

    it('shows error when assign response has no assignment id', async () => {
      const mutateAsyncSpy = vi.fn().mockResolvedValueOnce({}).mockResolvedValueOnce(undefined)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const user = userEvent.setup()
      render(<EditAssignmentDialog {...defaultProps} row={projectRow} />, { wrapper })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      await user.click(await screen.findByRole('option', { name: 'Viewer' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText(/did not include an assignment id/i)).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('shows error alert when mutation fails', async () => {
      const mutateAsyncSpy = vi.fn().mockRejectedValue(new Error('Network error'))
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onClose = vi.fn()
      const onSuccess = vi.fn()
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={projectRow} displayName="alice" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      // Change the role
      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)

      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        // mutateAsync was called but failed
        expect(mutateAsyncSpy).toHaveBeenCalled()
        // onSuccess should NOT be called on error
        expect(onSuccess).not.toHaveBeenCalled()
      })
    })

    it('does not call onSuccess when mutation rejects', async () => {
      const mutateAsyncSpy = vi.fn().mockRejectedValue({ detail: 'Server error' })
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={systemGroupRow} displayName="Ops" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      // Change role
      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalled()
        expect(onSuccess).not.toHaveBeenCalled()
        expect(onClose).not.toHaveBeenCalled()
      })
    })

    it('revokes new assignment when delete fails after assign (user)', async () => {
      // Assign new succeeds, delete old fails, revoke new succeeds
      const mutateAsyncSpy = vi
        .fn()
        .mockResolvedValueOnce({ id: 'new-assignment-id' })
        .mockRejectedValueOnce(new Error('Delete failed'))
        .mockResolvedValueOnce(undefined)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={systemUserRow} displayName="bob" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      const adminOption = await screen.findByRole('option', { name: 'Admin' })
      await user.click(adminOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalledTimes(3)
        expect(onSuccess).not.toHaveBeenCalled()
      })
    })

    it('revokes new assignment when delete fails after assign (system group)', async () => {
      const mutateAsyncSpy = vi
        .fn()
        .mockResolvedValueOnce({ id: 'new-assignment-id' })
        .mockRejectedValueOnce(new Error('Delete failed'))
        .mockResolvedValueOnce(undefined)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        ...mockMutationReturn,
        mutateAsync: mutateAsyncSpy,
      } as never)

      const onSuccess = vi.fn()
      const onClose = vi.fn()
      const user = userEvent.setup()
      render(<EditAssignmentDialog row={systemGroupRow} displayName="Ops" onClose={onClose} onSuccess={onSuccess} />, {
        wrapper,
      })

      const roleToggle = screen.getByPlaceholderText('Select a role...')
      await user.click(roleToggle)
      const viewerOption = await screen.findByRole('option', { name: 'Viewer' })
      await user.click(viewerOption)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mutateAsyncSpy).toHaveBeenCalledTimes(3)
        expect(onSuccess).not.toHaveBeenCalled()
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations for project-scoped assignment', async () => {
      const { container } = render(<EditAssignmentDialog {...defaultProps} />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations for system-scoped assignment', async () => {
      const { container } = render(<EditAssignmentDialog {...defaultProps} row={systemUserRow} displayName="bob" />, {
        wrapper,
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
