import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { PRINCIPAL_TYPE_HELP, ROLE_HELP } from '../../access/accessControlFieldHelpText'
import { useAllProjectRoles } from '../../access/useAllProjectRoles'

import { AssignProjectRoleModal } from './AssignProjectRoleModal'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../hooks/useDebouncedValue', () => ({
  useDebouncedValue: <T,>(value: T) => value,
}))

vi.mock('../../access/useAllProjectRoles', () => ({
  useAllProjectRoles: vi.fn(),
}))

const mockMutate = vi.fn()

const mockMutationReturn = {
  mutate: mockMutate,
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

const mockRoles = [
  {
    id: 'r1',
    name: 'project-admin',
    description: 'Project Admin',
    project_id: null,
    is_builtin: true,
    is_system_scoped: false,
    policies: [],
    labels: {},
    created_at: null,
    updated_at: null,
  },
  {
    id: 'r2',
    name: 'project-user',
    description: 'Project User',
    project_id: null,
    is_builtin: true,
    is_system_scoped: false,
    policies: [],
    labels: {},
    created_at: null,
    updated_at: null,
  },
  {
    id: 'r3',
    name: 'admin',
    description: 'Admin',
    project_id: null,
    is_builtin: true,
    is_system_scoped: false,
    policies: [],
    labels: {},
    created_at: null,
    updated_at: null,
  },
  {
    id: 'r4',
    name: 'custom-role',
    description: 'Custom',
    project_id: null,
    is_builtin: false,
    is_system_scoped: false,
    policies: [],
    labels: {},
    created_at: null,
    updated_at: null,
  },
]

const mockUsers = [
  { id: 'u1', username: 'alice', email: 'alice@test.com', first_name: 'Alice' },
  { id: 'u2', username: 'bob', email: 'bob@test.com', first_name: 'Bob' },
]

const mockGroups = [
  { id: 'g1', name: 'developers' },
  { id: 'g2', name: 'admins' },
]

function getTypeaheadInput(groupName: string) {
  return within(screen.getByRole('group', { name: groupName })).getByRole('textbox')
}

function queryTypeaheadInput(groupName: string) {
  const group = screen.queryByRole('group', { name: groupName })
  if (!group) return null
  return within(group).queryByRole('textbox')
}

describe('AssignProjectRoleModal', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()
  const emptyAssignedRoles = new Map<string, Set<string>>()

  function setupMocks() {
    vi.mocked(useAllProjectRoles).mockReturnValue({
      roles: mockRoles,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
      if (path === '/users/directory') {
        return {
          data: { resources: mockUsers, next: null },
          isPending: false,
          isLoading: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
      if (path === '/groups/directory') {
        return {
          data: { resources: mockGroups, next: null },
          isPending: false,
          isLoading: false,
          isError: false,
          error: null,
          isFetching: false,
          refetch: vi.fn(),
        } as never
      }
      return {
        data: undefined,
        isPending: false,
        isLoading: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never
    })

    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  function renderModal(isOpen = true, assignedRolesByPrincipal = emptyAssignedRoles) {
    return render(
      <AssignProjectRoleModal
        projectId="proj-1"
        isOpen={isOpen}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
        assignedRolesByPrincipal={assignedRolesByPrincipal}
      />,
      { wrapper }
    )
  }

  it('has no accessibility violations', async () => {
    const { container } = renderModal()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders the modal header', () => {
    renderModal()
    expect(screen.getByText('Assign role')).toBeInTheDocument()
  })

  it('renders principal type, user, and role form fields', () => {
    renderModal()
    expect(screen.getByLabelText('Principal type')).toBeInTheDocument()
    expect(getTypeaheadInput('User')).toBeInTheDocument()
    expect(getTypeaheadInput('Role')).toBeInTheDocument()
  })

  it('shows all project roles from the project endpoint', () => {
    renderModal()

    expect(screen.getByText('Role')).toBeInTheDocument()
  })

  it('shows principal type and role help on click', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByRole('button', { name: 'More info for Principal type' }))
    expect(screen.getByText(PRINCIPAL_TYPE_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Role' }))
    expect(screen.getByText(ROLE_HELP)).toBeInTheDocument()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockOnClose).toHaveBeenCalledOnce()
  })

  it('shows inline validation errors when Assign is clicked with empty fields', async () => {
    const user = userEvent.setup()
    renderModal()

    const assignButton = screen.getByRole('button', { name: 'Assign' })
    expect(assignButton).toBeEnabled()

    await user.click(assignButton)

    await waitFor(() => {
      expect(screen.getByText('User is required')).toBeInTheDocument()
      expect(screen.getByText('Role is required')).toBeInTheDocument()
    })
    expect(mockMutate).not.toHaveBeenCalled()
  })

  async function fillAndSubmitForm() {
    const user = userEvent.setup()
    renderModal()

    const userInput = getTypeaheadInput('User')
    await user.click(userInput)
    const aliceOption = await screen.findByRole('option', { name: /alice/i })
    await user.click(aliceOption)

    await waitFor(() => {
      expect(getTypeaheadInput('Role')).not.toBeDisabled()
    })

    const roleInput = getTypeaheadInput('Role')
    await user.click(roleInput)
    const roleOption = await screen.findByRole('option', { name: /project-admin/i })
    await user.click(roleOption)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Assign' })).not.toBeDisabled()
    })

    await user.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })
  }

  it('calls onSuccess on successful assignment', async () => {
    await fillAndSubmitForm()

    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    // eslint-disable-next-line @typescript-eslint/require-await
    await act(async () => {
      callbacks.onSuccess()
    })

    expect(mockOnSuccess).toHaveBeenCalled()
  })

  it('shows error on failed assignment', async () => {
    await fillAndSubmitForm()

    const callbacks = mockMutate.mock.calls[0][1] as { onError: (error: unknown) => void }
    act(() => {
      callbacks.onError(new Error('Server error'))
    })

    expect(mockOnSuccess).not.toHaveBeenCalled()
  })

  it('switches to group selector when principal type is changed to Group', async () => {
    const user = userEvent.setup()
    renderModal()

    const principalToggle = screen.getByRole('button', { name: 'Principal type' })
    await user.click(principalToggle)
    await user.click(screen.getByRole('option', { name: 'Group' }))

    expect(getTypeaheadInput('Group')).toBeInTheDocument()
    expect(queryTypeaheadInput('User')).not.toBeInTheDocument()
  })

  it('submits group assignment with correct body', async () => {
    const user = userEvent.setup()
    renderModal()

    const principalToggle = screen.getByRole('button', { name: 'Principal type' })
    await user.click(principalToggle)
    await user.click(screen.getByRole('option', { name: 'Group' }))

    const groupInput = getTypeaheadInput('Group')
    await user.click(groupInput)
    const groupOption = await screen.findByRole('option', { name: /developers/i })
    await user.click(groupOption)

    await waitFor(() => {
      expect(getTypeaheadInput('Role')).not.toBeDisabled()
    })

    const roleInput = getTypeaheadInput('Role')
    await user.click(roleInput)
    const roleOption = await screen.findByRole('option', { name: /project-admin/i })
    await user.click(roleOption)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Assign' })).not.toBeDisabled()
    })

    await user.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    const callArgs = mockMutate.mock.calls[0][0] as {
      body: { group_id: string; role_name: string }
    }
    expect(callArgs.body.group_id).toBe('g1')
    expect(callArgs.body.role_name).toBe('project-admin')
  })

  it('resets principal selection when switching principal type', async () => {
    const user = userEvent.setup()
    renderModal()

    const userInput = getTypeaheadInput('User')
    await user.click(userInput)
    const aliceOption = await screen.findByRole('option', { name: /alice/i })
    await user.click(aliceOption)

    const principalToggle = screen.getByRole('button', { name: 'Principal type' })
    await user.click(principalToggle)
    await user.click(screen.getByRole('option', { name: 'Group' }))

    const groupInput = getTypeaheadInput('Group')
    expect(groupInput).toHaveValue('')
  })
})
