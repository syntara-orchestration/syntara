import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { POLICIES_HELP } from './accessControlFieldHelpText'
import { EditRoleDialog } from './EditRoleDialog'
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockRole: RoleRead = {
  id: 'role-1',
  name: 'my-custom-role',
  description: 'A custom role for testing',
  policies: ['workflow-admin'],
  is_builtin: false,
  is_system_scoped: false,
  project_id: null,
  labels: {},
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
}

describe('EditRoleDialog', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()
  const mockMutate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    // Mock policies query (used by PolicySelect)
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: {
        resources: [
          { id: 'p1', name: 'workflow-admin', description: 'Manage workflows' },
          { id: 'p2', name: 'project-viewer', description: 'View projects' },
        ],
      },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    } as never)

    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: mockMutate,
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

  function renderDialog(role: RoleRead = mockRole) {
    return render(<EditRoleDialog role={role} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })
  }

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderDialog()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('field help popovers', () => {
    it('shows policies help on click and keeps name without a popover', async () => {
      const user = userEvent.setup()
      renderDialog()

      expect(screen.queryByRole('button', { name: 'More info for Name' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'More info for Policies' }))
      expect(screen.getByText(POLICIES_HELP)).toBeInTheDocument()
    })
  })

  describe('Rendering', () => {
    it('renders modal with "Edit Role" title', () => {
      renderDialog()
      expect(screen.getByText('Edit my-custom-role')).toBeInTheDocument()
    })

    it('pre-fills name input with role name', () => {
      renderDialog()
      expect(screen.getByRole('textbox', { name: /role name/i })).toHaveValue('my-custom-role')
    })

    it('pre-fills description input with role description', () => {
      renderDialog()
      expect(screen.getByRole('textbox', { name: /role description/i })).toHaveValue('A custom role for testing')
    })

    it('pre-fills policies with role policies', () => {
      renderDialog()
      expect(screen.getByText('workflow-admin')).toBeInTheDocument()
    })

    it('renders Save button', () => {
      renderDialog()
      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    })

    it('renders Cancel button', () => {
      renderDialog()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('shows helper text for name format', () => {
      renderDialog()
      expect(screen.getByText(/lowercase alphanumeric with hyphens/i)).toBeInTheDocument()
    })
  })

  describe('Form pre-population', () => {
    it('handles role with null description', () => {
      renderDialog({ ...mockRole, description: null })
      expect(screen.getByRole('textbox', { name: /role description/i })).toHaveValue('')
    })

    it('handles role with multiple policies', () => {
      renderDialog({ ...mockRole, policies: ['workflow-admin', 'project-viewer'] })
      expect(screen.getByText('workflow-admin')).toBeInTheDocument()
      expect(screen.getByText('project-viewer')).toBeInTheDocument()
    })
  })

  describe('Form validation', () => {
    it('shows error when name is cleared and submitted', async () => {
      const user = userEvent.setup()
      renderDialog()

      const nameInput = screen.getByRole('textbox', { name: /role name/i })
      await user.clear(nameInput)
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(screen.getByText('Name is required')).toBeInTheDocument()
      })
      expect(mockMutate).not.toHaveBeenCalled()
    })
  })

  describe('Form submission', () => {
    it('calls updateRole mutation with form data on valid submit', async () => {
      const user = userEvent.setup()
      renderDialog()

      // Modify the description
      const descInput = screen.getByRole('textbox', { name: /role description/i })
      await user.clear(descInput)
      await user.type(descInput, 'Updated description')

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        params: { path: { role_id: 'role-1' } },
        body: {
          name: 'my-custom-role',
          description: 'Updated description',
          policies: ['workflow-admin'],
        },
      })
    })

    it('calls onSuccess and onClose on successful mutation', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      expect(mockOnSuccess).toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()
      expect(screen.getByText('Role updated')).toBeInTheDocument()
      expect(screen.getByText('my-custom-role has been updated.')).toBeInTheDocument()
    })

    it('shows error on failed mutation without calling onSuccess/onClose', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callbacks = mockMutate.mock.calls[0][1] as { onError: (error: unknown) => void }
      act(() => {
        callbacks.onError(new Error('Server error'))
      })

      expect(mockOnSuccess).not.toHaveBeenCalled()
      expect(mockOnClose).not.toHaveBeenCalled()
    })

    it('sends undefined for empty description', async () => {
      const user = userEvent.setup()
      renderDialog()

      const descInput = screen.getByRole('textbox', { name: /role description/i })
      await user.clear(descInput)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: { description?: string } }]
      expect(callArgs[0].body.description).toBeUndefined()
    })
  })

  describe('Cancel', () => {
    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })
})
