import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { adminClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { useAuthStore } from '../../../stores/useAuthStore'
import { accessFetchClient } from '../../access/accessClient'

import { TokenRevocationTab } from './TokenRevocation'

vi.mock('../../../client', () => ({
  adminClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('../../../stores/useAuthStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      logout: vi.fn().mockResolvedValue(undefined),
    })),
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

describe('TokenRevocationTab', () => {
  const mockMutate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(adminClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as ReturnType<typeof adminClient.useMutation>)
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })
  })

  function renderWithQuery(data: { revoked_before: string | null; updated_at: string | null }) {
    vi.mocked(adminClient.useQuery).mockReturnValue({
      data,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    return render(<TokenRevocationTab />, { wrapper })
  }

  it('renders empty state when no revocation has occurred', () => {
    renderWithQuery({ revoked_before: null, updated_at: null })

    expect(screen.getByText('No global revocation has been performed')).toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke all tokens' })).toBeInTheDocument()
  })

  it('renders populated state with formatted timestamps', () => {
    renderWithQuery({
      revoked_before: '2024-06-15T14:30:00Z',
      updated_at: '2024-06-15T14:30:00Z',
    })

    expect(screen.queryByText('No global revocation has been performed')).not.toBeInTheDocument()
    expect(screen.queryByText('N/A')).not.toBeInTheDocument()
  })

  async function waitForButtonEnabled() {
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Revoke all tokens' })).not.toHaveAttribute('aria-disabled', 'true')
    })
  }

  it('opens confirmation dialog when revoke button is clicked', async () => {
    const user = userEvent.setup()
    renderWithQuery({ revoked_before: null, updated_at: null })
    await waitForButtonEnabled()

    await user.click(screen.getByRole('button', { name: 'Revoke all tokens' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/You will be signed out/)).toBeInTheDocument()
  })

  it('closes confirmation dialog on cancel', async () => {
    const user = userEvent.setup()
    renderWithQuery({ revoked_before: null, updated_at: null })
    await waitForButtonEnabled()

    await user.click(screen.getByRole('button', { name: 'Revoke all tokens' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('calls mutation on confirm', async () => {
    const user = userEvent.setup()
    renderWithQuery({ revoked_before: null, updated_at: null })
    await waitForButtonEnabled()

    await user.click(screen.getByRole('button', { name: 'Revoke all tokens' }))

    await user.click(screen.getByRole('checkbox', { name: /I understand all users will be signed out/i }))

    // The dialog has a second "Revoke all tokens" button (confirm)
    const buttons = screen.getAllByRole('button', { name: 'Revoke all tokens' })
    await user.click(buttons[buttons.length - 1])

    expect(mockMutate).toHaveBeenCalled()
    const callArgs = mockMutate.mock.calls[0] as [Record<string, unknown>, { onSuccess: () => void }]
    expect(callArgs[0]).toEqual({})
    expect(callArgs[1].onSuccess).toBeTypeOf('function')
  })

  it('calls logout on successful revocation', async () => {
    const mockLogout = vi.fn().mockResolvedValue(undefined)
    vi.mocked(useAuthStore.getState).mockReturnValue({
      logout: mockLogout,
    } as unknown as ReturnType<typeof useAuthStore.getState>)

    const user = userEvent.setup()
    renderWithQuery({ revoked_before: null, updated_at: null })
    await waitForButtonEnabled()

    await user.click(screen.getByRole('button', { name: 'Revoke all tokens' }))
    await user.click(screen.getByRole('checkbox', { name: /I understand all users will be signed out/i }))
    const buttons = screen.getAllByRole('button', { name: 'Revoke all tokens' })
    await user.click(buttons[buttons.length - 1])

    // Simulate the onSuccess callback — wrap in act because it triggers state updates
    const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => {
      callbacks.onSuccess()
    })

    expect(mockLogout).toHaveBeenCalled()
  })

  it('renders descriptive text explaining revocation', () => {
    renderWithQuery({ revoked_before: null, updated_at: null })

    expect(screen.getByText(/immediately invalidate every active session/)).toBeInTheDocument()
    expect(screen.getByText(/security incident/)).toBeInTheDocument()
  })

  it('disables revoke button when user lacks revoke permission', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })
    renderWithQuery({ revoked_before: null, updated_at: null })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Revoke all tokens' })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('enables revoke button when user has revoke permission', async () => {
    renderWithQuery({ revoked_before: null, updated_at: null })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Revoke all tokens' })).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('should have no accessibility violations', async () => {
    const { container } = renderWithQuery({ revoked_before: null, updated_at: null })
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  it('should have no accessibility violations when button is disabled', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })
    const { container } = renderWithQuery({ revoked_before: null, updated_at: null })
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })
})
