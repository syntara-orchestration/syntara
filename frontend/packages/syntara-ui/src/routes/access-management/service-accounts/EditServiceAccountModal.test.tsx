import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'

import { EditServiceAccountModal } from './EditServiceAccountModal'
import { DESCRIPTION_HELP, NAME_HELP } from './serviceAccountFieldHelpText'
import type { ServiceAccountRead } from './serviceAccountTypes'

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(),
  },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('EditServiceAccountModal', () => {
  const mockMutate = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  const mockServiceAccount: ServiceAccountRead = {
    id: 'sa-1',
    name: 'my-service-account',
    description: 'A test service account',
    status: 'active',
    project_id: '550e8400-e29b-41d4-a716-446655440000',
    last_authenticated_at: '2024-06-15T10:00:00Z',
    created_by: 'admin',
    updated_by: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    labels: {},
  }

  beforeEach(() => {
    vi.clearAllMocks()

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

  it('renders with "Edit service account" title', () => {
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    expect(screen.getByRole('heading', { name: 'Edit my-service-account' })).toBeInTheDocument()
  })

  it('pre-populates form fields with service account data', () => {
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('my-service-account')
    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue('A test service account')
  })

  it('shows name and description help on click', async () => {
    const user = userEvent.setup()
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    await user.click(screen.getByRole('button', { name: 'More info for Name' }))
    expect(screen.getByText(NAME_HELP)).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'More info for Description' }))
    expect(screen.getByText(DESCRIPTION_HELP)).toBeInTheDocument()
  })

  it('calls mutation with correct body on submit', async () => {
    const user = userEvent.setup()
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    const nameInput = screen.getByRole('textbox', { name: 'Name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'updated-name')

    await user.click(screen.getByRole('button', { name: 'Save service account' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        params: { path: { service_account_id: 'sa-1' } },
        body: {
          name: 'updated-name',
          description: 'A test service account',
        },
      })
    })
  })

  it('calls onClose and onSuccess after successful update', async () => {
    const user = userEvent.setup()
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    await user.click(screen.getByRole('button', { name: 'Save service account' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
      callbacks.onSuccess()
    })

    expect(mockOnClose).toHaveBeenCalled()
    expect(mockOnSuccess).toHaveBeenCalled()
  })

  it('shows validation error when name is empty', async () => {
    const user = userEvent.setup()
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    const nameInput = screen.getByRole('textbox', { name: 'Name' })
    await user.clear(nameInput)
    await user.click(screen.getByRole('button', { name: 'Save service account' }))

    await waitFor(() => {
      expect(screen.getByText('Name is required')).toBeInTheDocument()
    })
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={true}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('does not render form content when closed', () => {
    render(
      <EditServiceAccountModal
        serviceAccount={mockServiceAccount}
        isOpen={false}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper }
    )

    expect(screen.queryByRole('textbox', { name: 'Name' })).not.toBeInTheDocument()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <EditServiceAccountModal
          serviceAccount={mockServiceAccount}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />,
        { wrapper }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
