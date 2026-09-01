import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'

import { EditIdentityProvider } from './EditIdentityProvider'

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  OIDC_REDIRECT_URI: 'http://localhost/api/v1/auth/oidc/callback',
}))

vi.mock('../../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/authentication/identity-providers/provider-1',
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { MockLink } = await import('../../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => ({ providerId: 'provider-1' }),
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

const mockProvider = {
  id: 'provider-1',
  name: 'Azure AD',
  enabled: true,
  configuration: {
    provider_type: 'oidc',
    auto_discovery: true,
    issuer_url: 'https://login.microsoftonline.com/tenant',
    client_id: 'client-123',
    scopes: 'openid profile email',
  },
}

function setupMocks() {
  vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
    data: mockProvider,
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

describe('EditIdentityProvider', () => {
  it('renders the edit form with correct title', () => {
    setupMocks()
    render(<EditIdentityProvider />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Edit OIDC provider' })).toBeInTheDocument()
  })

  it('renders the Save provider submit button on last step', async () => {
    setupMocks()
    const user = userEvent.setup()
    render(<EditIdentityProvider />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
    expect(screen.getByRole('button', { name: 'Save provider' })).toBeInTheDocument()
  })

  it('populates form fields with provider data', () => {
    setupMocks()
    render(<EditIdentityProvider />, { wrapper })

    expect(screen.getByDisplayValue('Azure AD')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://login.microsoftonline.com/tenant')).toBeInTheDocument()
    expect(screen.getByDisplayValue('client-123')).toBeInTheDocument()
  })

  it('renders error state when provider not found', () => {
    const notFoundError = Object.assign(new Error('Not found'), { status: 404 })
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: notFoundError,
      refetch: vi.fn(),
    })
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    })

    render(<EditIdentityProvider />, { wrapper })

    expect(screen.getByText('Identity provider not found')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupMocks()
    const { container } = render(<EditIdentityProvider />, { wrapper })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
