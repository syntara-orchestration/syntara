import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'

import { AAPSetupModal } from './AAPSetupModal'

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('AAPSetupModal', () => {
  const mockMutate = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
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
    })
  })

  function renderModal(isOpen = true) {
    return render(<AAPSetupModal isOpen={isOpen} onClose={mockOnClose} onSuccess={mockOnSuccess} />, { wrapper })
  }

  async function selectAuthMethod(user: ReturnType<typeof userEvent.setup>, method: 'credentials' | 'token') {
    const label = method === 'token' ? /Personal access token/ : /Platform admin credentials/
    await user.click(screen.getByRole('button', { name: /Personal access token|Platform admin credentials/ }))
    const options = await screen.findAllByRole('option')
    const option = options.find((o) => label.test(o.textContent ?? ''))
    if (!option) throw new Error(`Option matching ${String(label)} not found`)
    await user.click(option)
  }

  describe('rendering', () => {
    it('renders the modal when open', () => {
      renderModal()

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Add Ansible Automation Platform as a provider' })).toBeInTheDocument()
    })

    it('renders common form fields and auth method select', () => {
      renderModal()

      expect(screen.getByLabelText('Ansible Automation Platform URL')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Personal access token' })).toBeInTheDocument()
      expect(screen.getByLabelText('Disable TLS certificate verification')).toBeInTheDocument()
    })

    it('renders token field by default', () => {
      renderModal()

      expect(screen.getByLabelText('Personal access token')).toBeInTheDocument()
    })

    it('renders action buttons', () => {
      renderModal()

      expect(screen.getByRole('button', { name: 'Add provider' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      renderModal(false)

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  describe('auth method selection', () => {
    it('shows credential fields when Platform admin credentials is selected', async () => {
      const user = userEvent.setup()
      renderModal()

      await selectAuthMethod(user, 'credentials')

      expect(screen.getByLabelText('Platform admin username')).toBeInTheDocument()
      expect(screen.getByLabelText('Platform admin password')).toBeInTheDocument()
      expect(screen.queryByLabelText('Personal access token')).not.toBeInTheDocument()
    })

    it('shows token field when switching back to Personal access token', async () => {
      const user = userEvent.setup()
      renderModal()

      await selectAuthMethod(user, 'credentials')
      await selectAuthMethod(user, 'token')

      expect(screen.getByLabelText('Personal access token')).toBeInTheDocument()
      expect(screen.queryByLabelText('Platform admin username')).not.toBeInTheDocument()
    })
  })

  describe('validation', () => {
    it('shows validation errors for empty required fields with token', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(await screen.findByText('Ansible Automation Platform URL is required')).toBeInTheDocument()
      expect(screen.getByText('Personal access token is required')).toBeInTheDocument()
      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows validation errors for empty admin credential fields', async () => {
      const user = userEvent.setup()
      renderModal()

      await selectAuthMethod(user, 'credentials')
      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(await screen.findByText('Platform admin username is required')).toBeInTheDocument()
      expect(screen.getByText('Platform admin password is required')).toBeInTheDocument()
      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows validation error for invalid URL', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'not-a-url')
      await user.type(screen.getByLabelText('Personal access token'), 'my-token')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(await screen.findByText('Must be a valid URL')).toBeInTheDocument()
      expect(mockMutate).not.toHaveBeenCalled()
    })
  })

  describe('submission', () => {
    it('calls the setup mutation with PAT payload', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await user.type(screen.getByLabelText('Personal access token'), 'my-secret-pat')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(mockMutate).toHaveBeenCalledOnce()
      const [params] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(params.body).toEqual({
        aap_url: 'https://aap.example.com',
        organization: 'Default',
        personal_access_token: 'my-secret-pat',
        insecure_skip_tls_verify: false,
      })
    })

    it('calls the setup mutation with admin credentials payload', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await selectAuthMethod(user, 'credentials')
      await user.type(screen.getByLabelText('Platform admin username'), 'admin')
      await user.type(screen.getByLabelText('Platform admin password'), 'secret123')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(mockMutate).toHaveBeenCalledOnce()
      const [params] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(params.body).toEqual({
        aap_url: 'https://aap.example.com',
        organization: 'Default',
        admin_username: 'admin',
        admin_password: 'secret123',
        insecure_skip_tls_verify: false,
      })
    })

    it('does not include admin credentials in PAT payload', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await user.type(screen.getByLabelText('Personal access token'), 'my-token')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      const [params] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(params.body).not.toHaveProperty('admin_username')
      expect(params.body).not.toHaveProperty('admin_password')
    })

    it('invokes onSuccess and shows alert on successful setup', async () => {
      const user = userEvent.setup()
      mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: (data: { name: string }) => void }) => {
        callbacks.onSuccess({ name: 'Ansible Automation Platform' })
      })
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await user.type(screen.getByLabelText('Personal access token'), 'my-token')
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(mockOnSuccess).toHaveBeenCalledOnce()
      expect(mockOnClose).toHaveBeenCalledOnce()
    })

    it('disables submit button while mutation is pending', () => {
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: mockMutate,
        isPending: true,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
        mutateAsync: vi.fn(),
        isIdle: false,
        isSuccess: false,
        failureCount: 0,
        failureReason: null,
        context: undefined,
        submittedAt: 0,
        variables: undefined,
        status: 'pending',
        isPaused: false,
      })

      renderModal()

      const submitButton = screen.getByRole('button', { name: /Add provider/i })
      expect(submitButton).toBeDisabled()
    })

    it('sends insecure_skip_tls_verify when toggled', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.type(screen.getByLabelText('Ansible Automation Platform URL'), 'https://aap.example.com')
      await user.type(screen.getByLabelText('Personal access token'), 'my-token')
      await user.click(screen.getByLabelText('Disable TLS certificate verification'))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      expect(mockMutate).toHaveBeenCalledOnce()
      const [params] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(params.body.insecure_skip_tls_verify).toBe(true)
    })
  })

  describe('cancel', () => {
    it('calls onClose when cancel is clicked', async () => {
      const user = userEvent.setup()
      renderModal()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations with admin credentials selected', async () => {
      const { container } = renderModal()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with token selected', async () => {
      const user = userEvent.setup()
      const { container } = renderModal()

      await selectAuthMethod(user, 'token')

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
