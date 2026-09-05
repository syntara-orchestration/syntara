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
    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  })

  function renderDialog(policy: ProjectPolicyRead = mockPolicy) {
    return render(
      <EditProjectPolicyDialog projectId="proj-1" policy={policy} onClose={mockOnClose} onSuccess={mockOnSuccess} />,
      { wrapper }
    )
  }

  it('has no accessibility violations', async () => {
    const { container } = renderDialog()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
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
