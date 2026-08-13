import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { adminClient, identityProvidersClient } from '../../../client'
import { useCanI } from '../../../hooks/useCanI'
import { AlertProvider } from '../../../providers/alerts'
import type { DocKey } from '../../../utils/docs/types'

import Authentication from './Authentication'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  adminClient: {
    useMutation: vi.fn().mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/authentication',
}))

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('../../../hooks/routing/navigate', () => ({
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

function setupEmptyProviders() {
  vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
    data: { resources: [], total: 0 },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as never)
  vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
  } as never)
  vi.mocked(adminClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never)
}

describe('Authentication', () => {
  beforeEach(() => {
    useDocLinkMock.mockClear()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
  })

  it('renders the page header', () => {
    setupEmptyProviders()
    render(<Authentication />, { wrapper })

    expect(screen.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeInTheDocument()
  })

  it('renders empty state when no providers configured', () => {
    setupEmptyProviders()
    render(<Authentication />, { wrapper })

    expect(screen.getByText('No identity providers configured')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add OIDC provider/ })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupEmptyProviders()
    const { container } = render(<Authentication />, { wrapper })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('does not show access denied while permission is loading', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })
    setupEmptyProviders()
    render(<Authentication />, { wrapper })

    expect(screen.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeInTheDocument()
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
  })

  describe('no access', () => {
    beforeEach(() => {
      vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    })

    it('shows access denied when user cannot read identity providers', () => {
      setupEmptyProviders()
      render(<Authentication />, { wrapper })

      expect(screen.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeInTheDocument()
      expect(screen.getByText('Access denied')).toBeInTheDocument()
      expect(screen.getByText(/You don't have permission to view identity providers/)).toBeInTheDocument()
      expect(screen.queryByText('No identity providers configured')).not.toBeInTheDocument()
    })

    it('has no accessibility violations in access denied state', async () => {
      setupEmptyProviders()
      const { container } = render(<Authentication />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('loading state', () => {
    it('shows header and empty panel while permission is loading', () => {
      vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })
      setupEmptyProviders()
      render(<Authentication />, { wrapper })

      expect(screen.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeInTheDocument()
      expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
      expect(screen.queryByText('No identity providers configured')).not.toBeInTheDocument()
    })

    it('has no accessibility violations while loading', async () => {
      vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })
      setupEmptyProviders()
      const { container } = render(<Authentication />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('page header', () => {
    it('includes Identity Providers heading', () => {
      setupEmptyProviders()
      render(<Authentication />, { wrapper })

      expect(screen.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeInTheDocument()
    })
  })

  describe('documentation link', () => {
    it('passes identityProviders doc link to header', () => {
      setupEmptyProviders()
      render(<Authentication />, { wrapper })

      expect(useDocLinkMock).toHaveBeenCalledWith('identityProviders')
      const docLink = screen.getByRole('link', { name: /documentation/i })
      expect(docLink).toHaveAttribute('href', 'https://docs.example/identityProviders')
    })
  })
})
