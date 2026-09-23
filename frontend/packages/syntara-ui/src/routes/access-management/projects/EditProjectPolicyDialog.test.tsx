import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import type { ProjectPolicyRead } from '../../access/types'

import { EditProjectPolicyDialog } from './EditProjectPolicyDialog'

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

const { mockNodeKinds } = vi.hoisted(() => ({ mockNodeKinds: { current: [] as unknown[] } }))

vi.mock('../../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    query: { isPending: false },
    nodeKinds: mockNodeKinds.current,
    nodeKindByKind: new Map(),
    disabledKinds: new Set<string>(),
  }),
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

const mockPolicy: ProjectPolicyRead = {
  id: 'p1',
  name: 'my-policy',
  description: 'A policy',
  statements: [{ effect: 'allow', actions: ['read'], scope: 'any' }],
  is_builtin: false,
  is_project_eligible: true,
  is_system_scoped: false,
  project_id: 'proj-1',
}

describe('EditProjectPolicyDialog', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockNodeKinds.current = []
    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  })

  function renderDialog(policy: ProjectPolicyRead = mockPolicy) {
    return render(
      <EditProjectPolicyDialog projectId="proj-1" policy={policy} onClose={mockOnClose} onSuccess={mockOnSuccess} />,
      { wrapper }
    )
  }

  function renderCreateDialog() {
    return render(<EditProjectPolicyDialog projectId="proj-1" onClose={mockOnClose} onSuccess={mockOnSuccess} />, {
      wrapper,
    })
  }

  it('renders create mode with empty fields', () => {
    renderCreateDialog()
    expect(screen.getByText('Create policy')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Policy name' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Policy description' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Policy statements JSON' })).toHaveValue('[]')
  })

  it('posts parsed statements and reports create success', async () => {
    const user = userEvent.setup()
    renderCreateDialog()
    await user.type(screen.getByRole('textbox', { name: 'Policy name' }), 'deny-scripts')
    const statements = '[{"effect":"deny","actions":["workflow_node:execute"],"scope":"project"}]'
    await user.clear(screen.getByRole('textbox', { name: 'Policy statements JSON' }))
    await user.click(screen.getByRole('textbox', { name: 'Policy statements JSON' }))
    await user.paste(statements)
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    expect(accessClient.useMutation).toHaveBeenCalledWith('post', '/projects/{project_id}/policies')
    expect(mockMutate.mock.calls[0][0]).toEqual({
      params: { path: { project_id: 'proj-1' } },
      body: {
        name: 'deny-scripts',
        description: undefined,
        statements: [{ effect: 'deny', actions: ['workflow_node:execute'], scope: 'project' }],
      },
    })
    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => callbacks.onSuccess())
    expect(await screen.findByText('Policy created')).toBeInTheDocument()
    expect(mockOnSuccess).toHaveBeenCalledOnce()
    expect(mockOnClose).toHaveBeenCalledOnce()
  })

  it('posts a statement appended by the builder', async () => {
    mockNodeKinds.current = [
      {
        kind: 'script',
        category: 'action',
        enabled: true,
        switchable: true,
        deniable_actions: ['write', 'execute'],
        can_write: true,
        attributes: [],
      },
    ]
    const user = userEvent.setup()
    renderCreateDialog()
    await user.type(screen.getByRole('textbox', { name: 'Policy name' }), 'deny-scripts')
    await user.click(screen.getByRole('button', { name: 'Select a node kind' }))
    await user.click(await screen.findByRole('option', { name: 'script' }))
    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    expect(mockMutate.mock.calls[0][0]).toMatchObject({
      body: {
        statements: [
          {
            effect: 'deny',
            actions: ['workflow_node:write'],
            scope: 'project',
            conditions: { resource_labels: { kind: 'script' } },
          },
        ],
      },
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderDialog()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('explains that the statements JSON is the saved policy definition', () => {
    renderCreateDialog()
    expect(screen.getByText(/The saved policy definition — a JSON array of statement objects/)).toBeInTheDocument()
  })

  it('renders the modal header', () => {
    renderDialog()
    expect(screen.getByText('Edit Project Policy')).toBeInTheDocument()
  })

  it('pre-populates the name field from the policy', () => {
    renderDialog()
    expect(screen.getByRole('textbox', { name: 'Policy name' })).toHaveValue('my-policy')
  })

  it('pre-populates the description field from the policy', () => {
    renderDialog()
    expect(screen.getByRole('textbox', { name: 'Policy description' })).toHaveValue('A policy')
  })

  it('renders the statements JSON in the textarea', () => {
    renderDialog()
    const textarea = screen.getByRole('textbox', { name: 'Policy statements JSON' })
    const expectedJson = JSON.stringify(mockPolicy.statements, null, 2)
    expect(textarea).toHaveValue(expectedJson)
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockOnClose).toHaveBeenCalledOnce()
  })

  it('calls onSuccess and onClose on successful mutation', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Save policy' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => {
      callbacks.onSuccess()
    })

    expect(mockOnSuccess).toHaveBeenCalled()
    expect(mockOnClose).toHaveBeenCalled()
  })

  it('shows error alert on failed mutation', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Save policy' }))

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
})
