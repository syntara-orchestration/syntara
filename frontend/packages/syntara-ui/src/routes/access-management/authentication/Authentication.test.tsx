import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

vi.mock('./identity-providers/AAPSetupModal', () => ({
  AAPSetupModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <dialog open>
        <button onClick={onClose}>Close</button>
      </dialog>
    ) : null,
}))

vi.mock('./useIdentityProviderPermissions', () => ({
  useIdentityProviderPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    canTest: true,
    canRevoke: true,
    isLoading: false,
    tooltips: { create: '', update: '', enable: '', delete: '', test: '', editMapping: '', revoke: '' },
  }),
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
  provider_type: 'oidc',
  configuration: {
    issuer_url: 'https://login.microsoftonline.com/tenant',
    client_id: 'client-123',
  },
}

function setupProviders(providers: (typeof mockProvider)[] = [mockProvider]) {
  vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
    data: { resources: providers, total: providers.length },
    isLoading: false,
    isError: false,
    error: null,
    isPending: false,
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

function setupEmptyProviders() {
  setupProviders([])
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

  it('keeps create actions in the empty-state footer, not the page header', () => {
    setupEmptyProviders()
    render(<Authentication />, { wrapper })

    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add OIDC provider/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add Ansible Automation Platform/ })).toBeInTheDocument()
  })

  it('shows create actions in the page header when providers exist', () => {
    setupProviders()
    render(<Authentication />, { wrapper })

    expect(screen.getByRole('button', { name: /Add OIDC provider/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add Ansible Automation Platform/ })).toBeInTheDocument()

    const filterBar = screen.getByRole('search', { name: /Filters/i })
    expect(within(filterBar).queryByRole('button', { name: /Add OIDC provider/ })).not.toBeInTheDocument()
    expect(within(filterBar).queryByRole('button', { name: /Add Ansible Automation Platform/ })).not.toBeInTheDocument()
  })

  it('opens AAP setup modal from the page header toolbar', async () => {
    setupProviders()
    const user = userEvent.setup()
    render(<Authentication />, { wrapper })

    await user.click(screen.getByRole('button', { name: /Add Ansible Automation Platform/ }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('hides Add Ansible Automation Platform in the header when an AAP provider exists', () => {
    const aapProvider = {
      ...mockProvider,
      id: 'aap-1',
      name: 'AAP',
      configuration: { ...mockProvider.configuration, idp_type: 'aap' },
    }
    setupProviders([aapProvider] as (typeof mockProvider)[])
    render(<Authentication />, { wrapper })

    expect(screen.queryByRole('button', { name: /Add Ansible Automation Platform/ })).not.toBeInTheDocument()
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
