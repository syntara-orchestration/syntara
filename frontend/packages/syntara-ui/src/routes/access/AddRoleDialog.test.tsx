import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { POLICIES_HELP, SCOPE_HELP } from './accessControlFieldHelpText'
import { AddRoleDialog } from './AddRoleDialog'
import { useSelectableProjects } from './useAllProjects'

const { mockPolicySelect } = vi.hoisted(() => ({
  mockPolicySelect: vi.fn(
    ({
      selected,
      onChange,
      scopeProjectId,
      projectEligible,
      isDisabled,
    }: {
      selected: string[]
      onChange: (policies: string[]) => void
      scopeProjectId?: string | null
      projectEligible?: boolean
      isDisabled?: boolean
    }) => (
      <div
        data-testid="policy-select"
        data-scope-project-id={scopeProjectId ?? ''}
        data-project-eligible={String(projectEligible ?? false)}
        data-disabled={String(isDisabled ?? false)}
      >
        <input
          placeholder="Select policies..."
          readOnly
          disabled={isDisabled}
          value={selected.join(', ')}
          onClick={() => onChange(['workflow-admin'])}
        />
      </div>
    )
  ),
}))

vi.mock('./PolicySelect', () => ({
  PolicySelect: mockPolicySelect,
}))

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

vi.mock('./useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('AddRoleDialog', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()
  const mockMutate = vi.fn()
  const mockProjectMutate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(useSelectableProjects).mockReturnValue({
      projects: [
        {
          id: 'proj-1',
          name: 'Project Alpha',
          description: undefined,
          labels: {},
          is_default: true,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
        },
        {
          id: 'proj-2',
          name: 'Project Beta',
          description: undefined,
          labels: {},
          is_default: false,
          created_at: '2024-03-01T00:00:00Z',
          updated_at: '2024-03-02T00:00:00Z',
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(accessClient.useQuery).mockImplementation(() => {
      // PolicySelect — /policies
      return {
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
      } as never
    })

    const idleMutation = {
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
      status: 'idle' as const,
      isPaused: false,
    }

    vi.mocked(accessClient.useMutation).mockImplementation((_method, path) => {
      const isProjectPath = String(path).includes('/projects/')
      return {
        ...idleMutation,
        mutate: isProjectPath ? mockProjectMutate : mockMutate,
      } as never
    })
  })

  function renderDialog(
    props: Partial<{
      defaultScope: 'system' | 'project'
      defaultProjectId: string
    }> = {}
  ) {
    return render(<AddRoleDialog onClose={mockOnClose} onSuccess={mockOnSuccess} {...props} />, { wrapper })
  }

  function selectPolicy(user: ReturnType<typeof userEvent.setup>) {
    return user.click(screen.getByPlaceholderText('Select policies...'))
  }

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderDialog()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders modal with "Create role" title', () => {
      renderDialog()
      expect(screen.getByRole('heading', { name: 'Create role' })).toBeInTheDocument()
    })

    it('renders name input', () => {
      renderDialog()
      expect(screen.getByRole('textbox', { name: /role name/i })).toBeInTheDocument()
    })

    it('renders description input', () => {
      renderDialog()
      expect(screen.getByRole('textbox', { name: /role description/i })).toBeInTheDocument()
    })

    it('renders Create role button', () => {
      renderDialog()
      expect(screen.getByRole('button', { name: 'Create role' })).toBeInTheDocument()
    })

    it('renders Cancel button', () => {
      renderDialog()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('shows helper text for name format', () => {
      renderDialog()
      expect(screen.getByText(/lowercase alphanumeric with hyphens/i)).toBeInTheDocument()
    })

    it('does not add a name help popover', () => {
      renderDialog()
      expect(screen.queryByRole('button', { name: 'More info for Name' })).not.toBeInTheDocument()
    })
  })

  describe('field help popovers', () => {
    it('shows scope and policies help on click', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'More info for Scope' }))
      expect(screen.getByText(SCOPE_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Policies' }))
      expect(screen.getByText(POLICIES_HELP)).toBeInTheDocument()
    })
  })

  describe('Form validation', () => {
    it('shows error when name is empty on submit', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(screen.getByText('Name is required')).toBeInTheDocument()
      })
      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows error when name has invalid characters', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'Invalid Name!')
      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(screen.getByText(/lowercase alphanumeric with hyphens, starting and ending/i)).toBeInTheDocument()
      })
      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows error when policies are empty on submit', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'valid-role')
      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(screen.getByText(/at least one policy/i)).toBeInTheDocument()
      })
      expect(mockMutate).not.toHaveBeenCalled()
    })
  })

  describe('Form submission', () => {
    it('calls createRole mutation with form data on valid submit', async () => {
      const user = userEvent.setup()
      renderDialog()

      // Fill in name
      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'my-role')
      // Fill in description
      await user.type(screen.getByRole('textbox', { name: /role description/i }), 'A test role')

      // Select a policy
      await selectPolicy(user)

      // Submit the form
      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        body: {
          name: 'my-role',
          description: 'A test role',
          policies: ['workflow-admin'],
        },
      })
    })

    it('calls onSuccess and onClose on successful mutation', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'my-role')

      // Select a policy
      await selectPolicy(user)

      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Invoke the onSuccess callback from the mutation
      const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      expect(mockOnSuccess).toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()
    })

    it('shows error on failed mutation', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'my-role')

      await selectPolicy(user)

      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Invoke the onError callback
      const callbacks = mockMutate.mock.calls[0][1] as { onError: (error: unknown) => void }
      act(() => {
        callbacks.onError(new Error('Server error'))
      })

      // onClose and onSuccess should NOT have been called
      expect(mockOnSuccess).not.toHaveBeenCalled()
      expect(mockOnClose).not.toHaveBeenCalled()
    })

    it('sends undefined for empty description', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'my-role')

      await selectPolicy(user)

      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: { description?: string } }]
      expect(callArgs[0].body.description).toBeUndefined()
    })

    it('calls project-scoped createRole when defaultScope is project', async () => {
      const user = userEvent.setup()
      renderDialog({ defaultScope: 'project', defaultProjectId: 'proj-1' })

      await user.type(screen.getByRole('textbox', { name: /role name/i }), 'proj-role')

      await selectPolicy(user)

      await user.click(screen.getByRole('button', { name: 'Create role' }))

      await waitFor(() => {
        expect(mockProjectMutate).toHaveBeenCalled()
      })
      expect(mockMutate).not.toHaveBeenCalled()

      const callArgs = mockProjectMutate.mock.calls[0] as [
        {
          params: { path: { project_id: string } }
          body: { name: string; policies: string[] }
        },
      ]
      expect(callArgs[0].params.path.project_id).toBe('proj-1')
      expect(callArgs[0].body).toEqual({
        name: 'proj-role',
        description: undefined,
        policies: ['workflow-admin'],
      })
    })
  })

  describe('PolicySelect scope', () => {
    it('passes null scopeProjectId for system scope by default', () => {
      renderDialog()

      expect(mockPolicySelect).toHaveBeenCalledWith(
        expect.objectContaining({
          scopeProjectId: null,
          projectEligible: false,
        }),
        undefined
      )
    })

    it('passes project scopeProjectId when defaultScope is project', () => {
      renderDialog({ defaultScope: 'project', defaultProjectId: 'proj-1' })

      expect(mockPolicySelect).toHaveBeenCalledWith(
        expect.objectContaining({
          scopeProjectId: 'proj-1',
          projectEligible: true,
          isDisabled: false,
        }),
        undefined
      )
    })

    it('disables PolicySelect until a project is chosen in project scope', async () => {
      const user = userEvent.setup()
      renderDialog()

      await user.click(screen.getByRole('button', { name: 'Role scope' }))
      await user.click(screen.getByRole('option', { name: 'Project' }))

      expect(mockPolicySelect).toHaveBeenLastCalledWith(
        expect.objectContaining({
          scopeProjectId: null,
          projectEligible: true,
          isDisabled: true,
        }),
        undefined
      )
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
