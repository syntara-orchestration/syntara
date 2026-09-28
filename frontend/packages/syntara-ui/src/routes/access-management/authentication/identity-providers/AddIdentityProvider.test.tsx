import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'

import { AddIdentityProvider } from './AddIdentityProvider'

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  OIDC_REDIRECT_URI: 'http://localhost/api/v1/auth/oidc/callback',
}))

vi.mock('../../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/authentication/identity-providers/add',
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { MockLink } = await import('../../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => ({}),
  }
})

vi.mock('../../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('../../../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function setupMocks() {
  vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })
  vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  })
}

describe('AddIdentityProvider', () => {
  it('renders the add form with correct title', () => {
    setupMocks()
    render(<AddIdentityProvider />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Add OIDC provider' })).toBeInTheDocument()
  })

  it('renders the Add provider submit button on last step', async () => {
    setupMocks()
    const user = userEvent.setup()
    render(<AddIdentityProvider />, { wrapper })

    expect(screen.queryByRole('button', { name: 'Add provider' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
    expect(screen.getByRole('button', { name: 'Add provider' })).toBeInTheDocument()
  })

  it('renders form fields', () => {
    setupMocks()
    render(<AddIdentityProvider />, { wrapper })

    expect(screen.getByLabelText(/Provider name/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Issuer URL/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Client secret/)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupMocks()
    const { container } = render(<AddIdentityProvider />, { wrapper })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
