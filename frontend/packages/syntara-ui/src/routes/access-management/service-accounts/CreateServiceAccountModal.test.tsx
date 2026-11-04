import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addDays, format } from 'date-fns'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { useSelectableProjects } from '../../access/useAllProjects'

import { CreateServiceAccountModal } from './CreateServiceAccountModal'
import { CREDENTIAL_EXPIRATION_HELP, DESCRIPTION_HELP, NAME_HELP } from './serviceAccountFieldHelpText'

const FUTURE_DATE = format(addDays(new Date(), 30), 'yyyy-MM-dd')

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(),
  },
}))

vi.mock('../../access/useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

vi.mock('../../../app/tanstackRouter', () => ({
  tanstackRouter: { navigate: vi.fn().mockResolvedValue(undefined) },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('CreateServiceAccountModal', () => {
  const mockCreateSAMutate = vi.fn()
  const mockCreateCredMutate = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(useSelectableProjects).mockReturnValue({
      projects: [
        { id: '550e8400-e29b-41d4-a716-446655440000', name: 'Project Alpha' },
        { id: '660e8400-e29b-41d4-a716-446655440001', name: 'Project Beta' },
      ],
    } as ReturnType<typeof useSelectableProjects>)

    vi.mocked(accessClient.useMutation).mockImplementation(((_method: string, endpoint: string) => {
      if (endpoint === '/service_accounts') {
        return {
          mutate: mockCreateSAMutate,
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
        }
      }
      return {
        mutate: mockCreateCredMutate,
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
      }
    }) as never)
  })

  describe('Form Phase', () => {
    it('renders with "Create service account" title', () => {
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Create service account' })).toBeInTheDocument()
    })

    it('renders name and description without a project', () => {
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.queryByRole('button', { name: 'Select a project' })).not.toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: 'Description' })).toBeInTheDocument()
    })

    it('renders credential expiration date field', () => {
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.getByLabelText('Credential expiration date')).toBeInTheDocument()
    })

    it('shows name, description, and credential expiration help on click', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })
      await user.click(screen.getByRole('button', { name: 'More info for Name' }))
      expect(screen.getByText(NAME_HELP)).toBeInTheDocument()
      expect(
        screen.getByText('Lowercase letters, numbers, and hyphens. Must start and end with a letter or number.')
      ).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Description' }))
      expect(screen.getByText(DESCRIPTION_HELP)).toBeInTheDocument()

      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'More info for Credential expiration date' }))
      expect(screen.getByText(CREDENTIAL_EXPIRATION_HELP)).toBeInTheDocument()
    })

    it('pre-populates expiration date with default value', () => {
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      const dateInput: HTMLInputElement = screen.getByLabelText('Credential expiration date')
      expect(dateInput.value).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })

    it('shows validation error when required fields are empty', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      const dateInput = screen.getByLabelText('Credential expiration date')
      await user.clear(dateInput)
      await user.type(dateInput, FUTURE_DATE)

      await user.click(screen.getByRole('button', { name: 'Create service account' }))

      await waitFor(() => {
        expect(screen.getByText('Name is required')).toBeInTheDocument()
      })
      expect(mockCreateSAMutate).not.toHaveBeenCalled()
    })

    it('validates expiration date on click before submit', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'my-new-sa')

      const dateInput = screen.getByLabelText('Credential expiration date')
      await user.clear(dateInput)

      const submitButton = screen.getByRole('button', { name: 'Create service account' })
      expect(submitButton).toBeEnabled()

      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Credential expiration date is required')).toBeInTheDocument()
      })
      expect(mockCreateSAMutate).not.toHaveBeenCalled()
    })

    it('calls create mutation with correct body on submit', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'my-new-sa')
      await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Test account')

      const dateInput = screen.getByLabelText('Credential expiration date')
      await user.clear(dateInput)
      await user.type(dateInput, FUTURE_DATE)

      await user.click(screen.getByRole('button', { name: 'Create service account' }))

      await waitFor(() => {
        expect(mockCreateSAMutate).toHaveBeenCalled()
        const callArgs = mockCreateSAMutate.mock.calls[0]
        expect(callArgs[0]).toEqual({
          body: {
            name: 'my-new-sa',
            description: 'Test account',
          },
        })
      })
    })

    it('calls onClose when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('does not render form content when closed', () => {
      render(<CreateServiceAccountModal isOpen={false} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      expect(screen.queryByRole('textbox', { name: 'Name' })).not.toBeInTheDocument()
    })
  })

  describe('Credentials Reveal Phase', () => {
    it('transitions to credential phase after successful create + credential', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'my-new-sa')

      const dateInput = screen.getByLabelText('Credential expiration date')
      await user.clear(dateInput)
      await user.type(dateInput, FUTURE_DATE)

      await user.click(screen.getByRole('button', { name: 'Create service account' }))

      await waitFor(() => {
        expect(mockCreateSAMutate).toHaveBeenCalled()
      })

      await waitFor(() => {
        const saCallbacks = mockCreateSAMutate.mock.calls[0][1] as { onSuccess: (data: unknown) => void }
        saCallbacks.onSuccess({ id: 'sa-new', name: 'my-new-sa', status: 'active' })
      })

      await waitFor(() => {
        expect(mockCreateCredMutate).toHaveBeenCalled()
      })

      await waitFor(() => {
        const credCallbacks = mockCreateCredMutate.mock.calls[0][1] as { onSuccess: (data: unknown) => void }
        credCallbacks.onSuccess({ identifier: 'cid-123', client_secret: 'secret-456' })
      })

      expect(screen.getByRole('heading', { name: 'Service account created' })).toBeInTheDocument()
      expect(screen.getByText('Save these credentials now')).toBeInTheDocument()
      expect(mockOnSuccess).toHaveBeenCalled()
    })
  })

  describe('Credential error fallback', () => {
    it('shows warning and navigates to credentials tab when credential creation fails', async () => {
      const user = userEvent.setup()
      render(<CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'my-new-sa')

      const dateInput = screen.getByLabelText('Credential expiration date')
      await user.clear(dateInput)
      await user.type(dateInput, FUTURE_DATE)

      await user.click(screen.getByRole('button', { name: 'Create service account' }))

      await waitFor(() => {
        expect(mockCreateSAMutate).toHaveBeenCalled()
      })

      act(() => {
        const saCallbacks = mockCreateSAMutate.mock.calls[0][1] as { onSuccess: (data: unknown) => void }
        saCallbacks.onSuccess({ id: 'sa-new', name: 'my-new-sa', status: 'active' })
      })

      await waitFor(() => {
        expect(mockCreateCredMutate).toHaveBeenCalled()
      })

      act(() => {
        const credCallbacks = mockCreateCredMutate.mock.calls[0][1] as { onError: () => void }
        credCallbacks.onError()
      })

      expect(mockOnSuccess).toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in form phase', async () => {
      const { container } = render(
        <CreateServiceAccountModal isOpen={true} onClose={mockOnClose} onSuccess={mockOnSuccess} />,
        { wrapper }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
