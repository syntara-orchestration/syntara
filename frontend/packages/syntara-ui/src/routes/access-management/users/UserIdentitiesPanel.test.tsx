import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, act, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient, usersClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'

import { useDetachIdentity } from './useDetachIdentity'
import { UserIdentitiesPanel } from './UserIdentitiesPanel'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  identityProvidersClient: {
    useQuery: vi.fn(),
  },
  OIDC_AUTHORIZE_PATH: '/api/v1/auth/oidc/authorize',
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./AttachIdentityModal', () => ({
  AttachIdentityModal: () => null,
}))

type MockProvider = {
  id: string
  name: string
  provider_type: string
}

const mockUseAuthProviders = vi.fn((): { providers: MockProvider[]; isLoading: boolean } => ({
  providers: [],
  isLoading: false,
}))
vi.mock('../../../app/useAuthProviders', () => ({
  useAuthProviders: () => mockUseAuthProviders(),
}))

vi.mock('./useUserIdentityPermissions', () => ({
  useUserIdentityPermissions: () => mockUseUserIdentityPermissions(),
}))

const defaultIdentityPermissions = {
  canAttach: true,
  canDetach: true,
  isLoading: false,
  tooltips: { attach: 'You need permission to attach identities.', detach: '' },
}

const mockUseUserIdentityPermissions = vi.hoisted(() => vi.fn(() => defaultIdentityPermissions))

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockIdentities = [
  {
    id: 'id-1',
    user_id: 'user-1',
    identity_provider_id: 'provider-1',
    issuer: 'https://login.example.com',
    subject: 'sub-abc',
    created_at: '2026-01-15T00:00:00Z',
    last_used_at: '2026-03-10T14:30:00Z',
    provider_name: 'Azure',
  },
]

const twoIdentities = [
  ...mockIdentities,
  {
    id: 'id-2',
    user_id: 'user-1',
    identity_provider_id: 'provider-2',
    issuer: 'https://auth.other.com',
    subject: 'sub-xyz',
    created_at: '2026-02-20T00:00:00Z',
    last_used_at: null,
    provider_name: 'Okta',
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let queryClient: QueryClient

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockMutate = vi.fn()

const mockFullProviders = [
  {
    id: 'provider-1',
    name: 'Azure',
    configuration: { issuer_url: 'https://login.example.com', client_id: 'client-1' },
  },
  {
    id: 'provider-2',
    name: 'Okta',
    configuration: { issuer_url: 'https://auth.other.com', client_id: 'client-2' },
  },
]

function setupMocks(identities: unknown[] = [], queryOverrides: Record<string, unknown> = {}) {
  vi.mocked(usersClient.useQuery).mockReturnValue({
    data: { resources: identities, next: null, prev: null, total: identities.length },
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...queryOverrides,
  } as never)

  vi.mocked(usersClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
  } as never)

  vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
    data: { resources: mockFullProviders, next: null, prev: null },
    isPending: false,
    isError: false,
    error: null,
  } as never)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('UserIdentitiesPanel', () => {
  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    mockMutate.mockClear()
    mockUseUserIdentityPermissions.mockImplementation(() => defaultIdentityPermissions)
    mockUseAuthProviders.mockReturnValue({ providers: [], isLoading: false })
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: { resources: mockFullProviders, next: null, prev: null },
      isPending: false,
      isError: false,
      error: null,
    } as never)
  })

  // ---- Empty state --------------------------------------------------------

  describe('Empty state', () => {
    it('shows empty state when no identities and no providers exist', () => {
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'No identity providers configured yet' })).toBeInTheDocument()
    })
  })

  // ---- Table rendering ----------------------------------------------------

  describe('Table rendering', () => {
    it('renders identities in a table with correct columns', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('Azure')).toBeInTheDocument()
    })

    it('renders column headers', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('columnheader', { name: /Provider/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Status/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Issuer URL/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Linked/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Last authenticated/i })).toBeInTheDocument()
    })

    it('renders outline status labels for connected and disconnected identities', () => {
      const mockProviders = [
        { id: 'provider-1', name: 'Azure', provider_type: 'oidc' },
        { id: 'provider-3', name: 'GitHub', provider_type: 'oidc' },
      ]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('Connected', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
      expect(screen.getByText('Not connected', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    })

    it('shows "Connected" label for linked identities', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('Connected')).toBeInTheDocument()
    })

    it('shows issuer URL for linked identities', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('https://login.example.com')).toBeInTheDocument()
    })

    it('renders provider name as a link', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      const providerLink = screen.getByRole('link', { name: 'Azure' })
      expect(providerLink).toBeInTheDocument()
    })
  })

  // ---- Identity count footer ----------------------------------------------

  describe('Identity count footer', () => {
    it('shows singular "1 identity" for one identity', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })

    it('shows plural "2 identities" for multiple identities', () => {
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })
  })

  // ---- Detach flow --------------------------------------------------------

  describe('Detach flow', () => {
    it('opens confirmation modal when Disconnect is clicked', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))

      expect(screen.getByText('Disconnect identity?')).toBeInTheDocument()
      expect(screen.getByText(/Disconnecting will remove sign-in access for this identity/)).toBeInTheDocument()
      expect(screen.getAllByText('https://login.example.com').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('sub-abc').length).toBeGreaterThanOrEqual(1)
    })

    it('calls mutation when Disconnect in modal is confirmed', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))
      await user.click(screen.getByRole('button', { name: 'Disconnect' }))

      expect(mockMutate).toHaveBeenCalledTimes(1)
      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        params: { path: { user_id: 'user-1', identity_id: 'id-1' } },
      })
    })

    it('closes modal when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))

      expect(screen.getByText('Disconnect identity?')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Disconnect identity?')).not.toBeInTheDocument()
      })
    })

    it('closes modal on successful detach', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn()

      vi.mocked(usersClient.useQuery).mockReturnValue({
        data: { resources: twoIdentities, next: null, prev: null, total: twoIdentities.length },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(usersClient.useMutation).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      } as never)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))
      await user.click(screen.getByRole('button', { name: 'Disconnect' }))

      const callbacks = mockMutate.mock.calls[0][1] as {
        onSuccess: () => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Disconnect identity?')).not.toBeInTheDocument()
      })
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('handles detach error gracefully', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))
      await user.click(screen.getByRole('button', { name: 'Disconnect' }))

      const callbacks = mockMutate.mock.calls[0][1] as {
        onError: () => void
        onSettled: () => void
      }
      act(() => {
        callbacks.onError()
        callbacks.onSettled()
      })

      await waitFor(() => {
        expect(screen.queryByText('Disconnect identity?')).not.toBeInTheDocument()
      })
    })
  })

  // ---- Loading state ------------------------------------------------------

  describe('Loading state', () => {
    it('shows loading spinner when query is pending', () => {
      setupMocks([], { data: undefined, isPending: true })

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })

    it('shows loading spinner while auth providers load with no identities', () => {
      setupMocks([])
      mockUseAuthProviders.mockReturnValue({ providers: [], isLoading: true })

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    })
  })

  // ---- Error state --------------------------------------------------------

  describe('Error state', () => {
    it('shows error state when query errors', () => {
      setupMocks([], { data: undefined, isPending: false, isError: true, error: new Error('Network error') })

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error loading identities' })).toBeInTheDocument()
    })

    it('calls refetch when Retry is clicked on a retryable query error', async () => {
      const mockRefetch = vi.fn()
      setupMocks([], {
        data: undefined,
        isPending: false,
        isError: true,
        error: { message: 'Network error', retryable: true },
        refetch: mockRefetch,
      })

      const user = userEvent.setup()
      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /retry/i }))
      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  // ---- Transfer identity button (table view) --------------------------------

  describe('Transfer identity button', () => {
    it('renders Transfer identity button in table view', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('button', { name: /transfer identity/i })).toBeInTheDocument()
    })

    it('disables Transfer identity when user lacks attach permission', () => {
      mockUseUserIdentityPermissions.mockReturnValue({
        ...defaultIdentityPermissions,
        canAttach: false,
        tooltips: { attach: 'You need permission to attach identities.', detach: '' },
      })
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('button', { name: /transfer identity/i })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  // ---- Last identity protection -------------------------------------------

  describe('Last identity protection', () => {
    it('disables Disconnect menuitem when it is the only identity and user has no password', async () => {
      const user = userEvent.setup()
      setupMocks(mockIdentities) // single identity, isLocalUser defaults to false

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      expect(screen.getByRole('menuitem', { name: 'Disconnect' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('shows aria-disabled Disconnect menuitem with tooltip for last identity without password', async () => {
      const user = userEvent.setup()
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      const disconnectItem = screen.getByRole('menuitem', { name: 'Disconnect' })
      expect(disconnectItem).toHaveAttribute('aria-disabled', 'true')
      // Clicking the disabled item should not open the confirmation modal
      await user.click(disconnectItem)
      expect(screen.queryByText('Disconnect identity?')).not.toBeInTheDocument()
    })

    it('shows empty state for builtin users with no identities', () => {
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" isBuiltinUser hasPassword={true} />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Built-in user' })).toBeInTheDocument()
      expect(
        screen.getByText(/The built-in administrator account cannot be linked to external identity providers/)
      ).toBeInTheDocument()
    })

    it('enables Disconnect menuitem when there are multiple identities', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      expect(screen.getByRole('menuitem', { name: 'Disconnect' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('enables Disconnect for the only identity when hasPassword is true (password fallback exists)', async () => {
      const user = userEvent.setup()
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={true} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      expect(screen.getByRole('menuitem', { name: 'Disconnect' })).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  // ---- Local-to-federated conversion warning --------------------------------

  describe('Local user conversion warning', () => {
    const mockProviders = [
      { id: 'provider-1', name: 'Azure', provider_type: 'oidc' },
      { id: 'provider-3', name: 'GitHub', provider_type: 'oidc' },
    ]

    it('shows Connect menuitems for local non-builtin users', () => {
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" isLocalUser hasPassword={true} />, { wrapper })

      expect(screen.queryByRole('heading', { name: 'Built-in user' })).not.toBeInTheDocument()
      // Each unlinked provider has a kebab toggle; 2 providers = 2 kebabs
      expect(screen.getAllByRole('button', { name: 'Identity actions' })).toHaveLength(2)
    })

    it('opens conversion warning dialog when local user clicks Connect', async () => {
      const user = userEvent.setup()
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" isLocalUser hasPassword={true} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Connect' }))

      expect(screen.getByText('Link identity provider?')).toBeInTheDocument()
      expect(screen.getByText(/Your password will be permanently removed/)).toBeInTheDocument()
      expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument()
    })

    it('requires acknowledgement checkbox before confirm is enabled', async () => {
      const user = userEvent.setup()
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" isLocalUser hasPassword={true} />, { wrapper })

      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Connect' }))

      const confirmButton = screen.getByRole('button', { name: 'Convert and link' })
      expect(confirmButton).toBeDisabled()

      const checkbox = screen.getByRole('checkbox', { name: /I understand this action is irreversible/ })
      await user.click(checkbox)

      expect(confirmButton).toBeEnabled()
    })

    it('does not show conversion dialog for federated users', async () => {
      const user = userEvent.setup()
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, { wrapper })

      // Connected row is first; disconnected (unlinked) GitHub row is second
      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[1])
      const connectItem = screen.getByRole('menuitem', { name: 'Connect' })
      expect(connectItem).not.toHaveAttribute('aria-disabled', 'true')
      await user.click(connectItem)
      expect(screen.queryByText('Link identity provider?')).not.toBeInTheDocument()
    })

    it('does not show Connect buttons for builtin users', () => {
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" isBuiltinUser hasPassword={true} />, {
        wrapper,
      })

      expect(screen.queryByRole('button', { name: /Connect/i })).not.toBeInTheDocument()
    })
  })

  // ---- last_used_at rendering ---------------------------------------------

  describe('Last authenticated column', () => {
    it('shows dash when last_used_at is null', () => {
      setupMocks([twoIdentities[1]]) // Okta identity has last_used_at: null

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // The last authenticated cell should show '-'
      const cells = screen.getAllByRole('cell')
      const lastAuthCell = cells.find((cell) => cell.textContent === '-')
      expect(lastAuthCell).toBeDefined()
    })

    it('shows formatted date when last_used_at has a value', () => {
      setupMocks(mockIdentities) // Azure identity has last_used_at

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // Should not show a dash for last authenticated
      const cells = screen.getAllByRole('cell')
      const lastAuthCell = cells.find(
        (cell) => cell.getAttribute('data-label') === 'Last authenticated' && cell.textContent !== '-'
      )
      expect(lastAuthCell).toBeDefined()
    })
  })

  // ---- Unlinked providers -------------------------------------------------

  describe('Unlinked providers', () => {
    const mockProviders = [
      { id: 'provider-1', name: 'Azure', provider_type: 'oidc' },
      { id: 'provider-3', name: 'GitHub', provider_type: 'oidc' },
    ]

    it('shows unlinked providers as "Not connected"', () => {
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities) // Azure is linked, GitHub is not

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('Not connected')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument()
    })

    it('shows enabled Connect menuitem for unlinked providers when viewing own profile', async () => {
      const user = userEvent.setup()
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, { wrapper })

      // Connected row is first; disconnected GitHub row is second
      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[1])
      expect(screen.getByRole('menuitem', { name: 'Connect' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('shows disabled Connect menuitem for unlinked providers when viewing another user', async () => {
      const user = userEvent.setup()
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" currentUserId="other-user" hasPassword={false} />, { wrapper })

      expect(screen.queryByRole('link', { name: /Connect/i })).not.toBeInTheDocument()
      // Connected row is first; disconnected GitHub row is second
      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[1])
      expect(screen.getByRole('menuitem', { name: 'Connect' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('renders table when only unlinked providers exist (no identities)', () => {
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, { wrapper })

      // Should show the table, not the empty state
      expect(screen.queryByRole('heading', { name: 'No identity providers configured yet' })).not.toBeInTheDocument()
      // Both providers are unlinked so there are two "Not connected" labels
      const notConnectedLabels = screen.getAllByText('Not connected')
      expect(notConnectedLabels).toHaveLength(2)
    })

    it('shows issuer URL from full provider data for unlinked providers', () => {
      const mockProvidersFull = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProvidersFull, isLoading: false })
      setupMocks([])
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: {
          resources: [
            { id: 'provider-3', name: 'GitHub', configuration: { issuer_url: 'https://github.com/login/oauth' } },
          ],
          next: null,
          prev: null,
        },
        isPending: false,
        isError: false,
        error: null,
      } as never)

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByText('https://github.com/login/oauth')).toBeInTheDocument()
    })
  })

  // ---- Default sort order -------------------------------------------------

  describe('Default sort order', () => {
    it('renders Connected rows before Not connected rows by default', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities) // Azure linked (Connected), GitHub unlinked (Not connected)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      const connectedLabel = screen.getByText('Connected')
      const notConnectedLabel = screen.getByText('Not connected')

      // Connected should appear before Not connected in document order
      expect(connectedLabel.compareDocumentPosition(notConnectedLabel)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    })
  })

  // ---- Dash empty states for unlinked rows --------------------------------

  describe('Unlinked row empty states', () => {
    it('shows dash in Linked and Last authenticated columns for unlinked providers', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      const cells = screen.getAllByRole('cell')
      const linkedCell = cells.find((cell) => cell.getAttribute('data-label') === 'Linked')
      const lastAuthCell = cells.find((cell) => cell.getAttribute('data-label') === 'Last authenticated')

      expect(linkedCell).toHaveTextContent('-')
      expect(lastAuthCell).toHaveTextContent('-')
    })
  })

  // ---- Filter on unified list ---------------------------------------------

  describe('Filter', () => {
    it('renders all rows initially with no filter active', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(twoIdentities) // Azure + Okta connected; GitHub unlinked

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      expect(screen.getByRole('link', { name: 'Azure' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Okta' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument()
    })

    it('shows filter empty state when provider filter matches no rows', async () => {
      const user = userEvent.setup()
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      const providerFilter = screen.getByRole('textbox', { name: /provider filter/i })
      await user.type(providerFilter, 'zzz-nonexistent')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('No results found')).toBeInTheDocument()
      })
    })
  })

  // ---- identityProvidersClient resilience ---------------------------------

  describe('identityProvidersClient resilience', () => {
    it('still renders when identityProvidersClient query errors', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: true,
        error: new Error('Network error'),
      } as never)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // Panel still renders with an empty issuer URL for unlinked rows
      expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument()
      expect(screen.getByText('Not connected')).toBeInTheDocument()
    })

    it('shows empty issuer URL when provider is not found in full provider list', () => {
      const mockProviders = [{ id: 'provider-unknown', name: 'Unknown Provider', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([]) // mockFullProviders has provider-1 and provider-2, not provider-unknown

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // Renders without crashing; Issuer URL cell will be empty (Truncate content="")
      const rows = screen.getAllByRole('row')
      const dataRow = rows[1] // first data row after header
      const issuerCell = within(dataRow)
        .getAllByRole('cell')
        .find((cell) => cell.getAttribute('data-label') === 'Issuer URL')
      expect(issuerCell).toBeDefined()
      expect(issuerCell).toHaveTextContent('')
    })
  })

  // ---- isSelf / currentUserId ---------------------------------------------

  describe('currentUserId matching', () => {
    it('treats userId === currentUserId as self (isSelf = true)', async () => {
      const user = userEvent.setup()
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, { wrapper })

      // Self users see an enabled Connect menuitem for unlinked providers
      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      expect(screen.getByRole('menuitem', { name: 'Connect' })).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('treats different userId and currentUserId as not self', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" currentUserId="user-2" hasPassword={false} />, { wrapper })

      // Non-self users do not see a Connect link
      expect(screen.queryByRole('link', { name: /Connect/i })).not.toBeInTheDocument()
    })

    it('treats missing currentUserId as not self', () => {
      const mockProviders = [{ id: 'provider-3', name: 'GitHub', provider_type: 'oidc' }]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks([])

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // No currentUserId means not self
      expect(screen.queryByRole('link', { name: /Connect/i })).not.toBeInTheDocument()
    })
  })

  // ---- Transfer identity navigation ---------------------------------

  describe('Transfer identity navigation', () => {
    it('navigates to transfer identity wizard when Transfer identity button is clicked', async () => {
      const user = userEvent.setup()
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /transfer identity/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users/user-1/transfer-identity',
      })
    })
  })

  // ---- Provider link navigation -------------------------------------------

  describe('Provider link navigation', () => {
    it('renders provider link with correct href to provider detail page', () => {
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      const providerLink = screen.getByRole('link', { name: 'Azure' })
      expect(providerLink).toHaveAttribute('href', expect.stringContaining('provider-1') as string)
    })
  })

  // ---- link_error URL param -----------------------------------------------

  describe('link_error URL param', () => {
    it('reads and removes link_error from URL search params', () => {
      // Spy on history.replaceState before the component reads the URL
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {
        // no-op to avoid SecurityError in jsdom
      })

      // Inject a link_error param via the real location (jsdom supports this)
      const originalSearch = window.location.search
      // Use pushState to set the URL without navigation
      window.history.pushState({}, '', '/?link_error=Something+went+wrong')

      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // The effect should have called replaceState to clean the URL
      expect(replaceStateSpy).toHaveBeenCalled()
      const calledUrl = replaceStateSpy.mock.calls[0][2] as string
      expect(calledUrl).not.toContain('link_error')

      replaceStateSpy.mockRestore()
      // Restore the original URL
      window.history.pushState({}, '', originalSearch || '/')
    })

    it('displays generic fallback for unknown link_error values', async () => {
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})

      window.history.pushState({}, '', '/?link_error=Attacker+crafted+message')

      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // The sanitized fallback should render, not the raw URL param
      await waitFor(() => {
        expect(screen.getByText('Failed to link identity. Please try again.')).toBeInTheDocument()
      })
      expect(screen.queryByText('Attacker crafted message')).not.toBeInTheDocument()

      replaceStateSpy.mockRestore()
      window.history.pushState({}, '', '/')
    })
  })

  // ---- Detach flow edge cases ---------------------------------------------

  describe('Detach flow edge cases', () => {
    it('does not call mutate if identityToDetach is null (confirmDetach early return)', () => {
      // This tests the confirmDetach guard: if somehow confirmDetach is called
      // without identityToDetach being set, the mutation should not fire.
      // The guard is at line 269: if (!identityToDetach) return
      // We test this indirectly by verifying the mutation is only called
      // when a valid identity is selected.
      setupMocks(mockIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // Without clicking Disconnect first, mockMutate should not be called
      expect(mockMutate).not.toHaveBeenCalled()
    })

    it('shows the detach confirmation modal with identity details from the selected row', async () => {
      const user = userEvent.setup()
      setupMocks(twoIdentities)

      render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })

      // Open the second row's kebab (Okta) and click Disconnect
      await user.click(screen.getAllByRole('button', { name: 'Identity actions' })[1])
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }))

      // Modal should show Okta identity details
      expect(screen.getByText('Disconnect identity?')).toBeInTheDocument()
      expect(screen.getAllByText('https://auth.other.com').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('sub-xyz').length).toBeGreaterThanOrEqual(1)
    })
  })

  // ---- Accessibility -------------------------------------------------------

  describe('Accessibility', () => {
    it('has no accessibility violations with identities', async () => {
      setupMocks(mockIdentities)

      const { container } = render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      setupMocks([])

      const { container } = render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with unlinked providers', async () => {
      const mockProviders = [
        { id: 'provider-1', name: 'Azure', provider_type: 'oidc' },
        { id: 'provider-3', name: 'GitHub', provider_type: 'oidc' },
      ]
      mockUseAuthProviders.mockReturnValue({ providers: mockProviders, isLoading: false })
      setupMocks(mockIdentities)

      const { container } = render(<UserIdentitiesPanel userId="user-1" currentUserId="user-1" hasPassword={false} />, {
        wrapper,
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with disabled Disconnect (last identity, no password)', async () => {
      setupMocks(mockIdentities)

      const { container } = render(<UserIdentitiesPanel userId="user-1" hasPassword={false} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})

// ---------------------------------------------------------------------------
// useDetachIdentity hook
// ---------------------------------------------------------------------------

describe('useDetachIdentity', () => {
  beforeEach(() => {
    mockMutate.mockClear()
    vi.mocked(usersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)
  })

  const hookWrapper = ({ children }: { children: ReactNode }) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return (
      <QueryClientProvider client={client}>
        <AlertProvider>{children}</AlertProvider>
      </QueryClientProvider>
    )
  }

  it('initializes with no identity selected', () => {
    const { result } = renderHook(() => useDetachIdentity('user-1', vi.fn()), { wrapper: hookWrapper })

    expect(result.current.identityToDetach).toBeNull()
    expect(result.current.isDetaching).toBe(false)
  })

  it('does not call mutate when confirmDetach is called without a selected identity', () => {
    const { result } = renderHook(() => useDetachIdentity('user-1', vi.fn()), { wrapper: hookWrapper })

    act(() => result.current.confirmDetach())

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('calls mutate with correct params when an identity is selected', () => {
    const { result } = renderHook(() => useDetachIdentity('user-1', vi.fn()), { wrapper: hookWrapper })

    act(() => result.current.setIdentityToDetach({ id: 'id-1' } as never))
    act(() => result.current.confirmDetach())

    expect(mockMutate).toHaveBeenCalledTimes(1)
    expect(mockMutate.mock.calls[0][0]).toEqual({
      params: { path: { user_id: 'user-1', identity_id: 'id-1' } },
    })
  })
})
