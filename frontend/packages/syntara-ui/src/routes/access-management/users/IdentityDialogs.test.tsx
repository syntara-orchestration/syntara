import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { usersClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { IdentityActionsKebab, IdentityDialogs, type ConvertProviderInfo } from './IdentityDialogs'
import type { UserIdentity } from './identityUtils'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockIdentity: UserIdentity = {
  id: 'id-1',
  user_id: 'user-1',
  identity_provider_id: 'provider-1',
  issuer: 'https://login.example.com',
  subject: 'sub-abc',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
  last_used_at: '2026-03-10T14:30:00Z',
  provider_name: 'Azure',
}

const mockConvertProvider: ConvertProviderInfo = {
  name: 'GitHub',
  authorizeUrl: '/oidc/authorize?provider_id=gh-1&flow=link',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function setupMocks() {
  vi.mocked(usersClient.useQuery).mockReturnValue({
    data: { resources: [] },
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as never)

  vi.mocked(usersClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never)
}

const defaultDialogProps = {
  isAttachOpen: false,
  onCloseAttach: vi.fn(),
  currentUserId: 'user-1',
  onAttached: vi.fn(),
  identityToDetach: null as UserIdentity | null,
  isDetaching: false,
  onConfirmDetach: vi.fn(),
  onCancelDetach: vi.fn(),
  convertProvider: null as ConvertProviderInfo | null,
  onCloseConvert: vi.fn(),
  onConfirmConvert: vi.fn(),
}

function renderDialogs(overrides: Partial<typeof defaultDialogProps> = {}) {
  const props = { ...defaultDialogProps, ...overrides }
  return { ...render(<IdentityDialogs {...props} />, { wrapper }), props }
}

// ---------------------------------------------------------------------------
// IdentityDialogs
// ---------------------------------------------------------------------------

describe('IdentityDialogs', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.clearAllMocks()
    setupMocks()
  })

  // ---- Detach dialog -------------------------------------------------------

  describe('DetachConfirmModal', () => {
    it('does not render when identityToDetach is null', () => {
      renderDialogs({ identityToDetach: null })

      expect(screen.queryByText('Disconnect identity?')).not.toBeInTheDocument()
    })

    it('renders identity details when identityToDetach is set', () => {
      renderDialogs({ identityToDetach: mockIdentity })

      expect(screen.getByText('Disconnect identity?')).toBeInTheDocument()
      expect(screen.getByText('Azure')).toBeInTheDocument()
      expect(screen.getByText('https://login.example.com')).toBeInTheDocument()
      expect(screen.getByText('sub-abc')).toBeInTheDocument()
    })

    it('calls onConfirmDetach when Disconnect is clicked', async () => {
      const user = userEvent.setup()
      const { props } = renderDialogs({ identityToDetach: mockIdentity })

      await user.click(screen.getByRole('button', { name: 'Disconnect identity' }))

      expect(props.onConfirmDetach).toHaveBeenCalledTimes(1)
    })

    it('calls onCancelDetach when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const { props } = renderDialogs({ identityToDetach: mockIdentity })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(props.onCancelDetach).toHaveBeenCalledTimes(1)
    })

    it('disables Disconnect button while detaching', () => {
      renderDialogs({ identityToDetach: mockIdentity, isDetaching: true })

      expect(screen.getByRole('button', { name: /Disconnect/ })).toBeDisabled()
    })

    it('has no accessibility violations', async () => {
      const { baseElement } = renderDialogs({ identityToDetach: mockIdentity })

      const results = await axe(baseElement)
      expect(results).toHaveNoViolations()
    })
  })

  // ---- Convert dialog ------------------------------------------------------

  describe('ConvertConfirmDialog', () => {
    it('does not render when convertProvider is null', () => {
      renderDialogs({ convertProvider: null })

      expect(screen.queryByText('Link identity provider?')).not.toBeInTheDocument()
    })

    it('renders conversion warning when convertProvider is set', () => {
      renderDialogs({ convertProvider: mockConvertProvider })

      expect(screen.getByText('Link identity provider?')).toBeInTheDocument()
      expect(screen.getByText(/GitHub/)).toBeInTheDocument()
      expect(screen.getByText('Your password will be permanently removed')).toBeInTheDocument()
      expect(screen.getByText('This action cannot be undone')).toBeInTheDocument()
    })

    it('has confirm button disabled until acknowledgement checkbox is checked', async () => {
      const user = userEvent.setup()
      renderDialogs({ convertProvider: mockConvertProvider })

      const confirmButton = screen.getByRole('button', { name: 'Convert and link identity' })
      expect(confirmButton).toBeDisabled()

      const checkbox = screen.getByRole('checkbox', { name: 'I understand this action is irreversible' })
      await user.click(checkbox)

      expect(confirmButton).toBeEnabled()
    })

    it('calls onConfirmConvert when confirmed after acknowledgement', async () => {
      const user = userEvent.setup()
      const { props } = renderDialogs({ convertProvider: mockConvertProvider })

      await user.click(screen.getByRole('checkbox', { name: 'I understand this action is irreversible' }))
      await user.click(screen.getByRole('button', { name: 'Convert and link identity' }))

      expect(props.onConfirmConvert).toHaveBeenCalledTimes(1)
    })

    it('calls onCloseConvert when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const { props } = renderDialogs({ convertProvider: mockConvertProvider })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(props.onCloseConvert).toHaveBeenCalledTimes(1)
    })

    it('has no accessibility violations', async () => {
      const { baseElement } = renderDialogs({ convertProvider: mockConvertProvider })

      const results = await axe(baseElement)
      expect(results).toHaveNoViolations()
    })
  })

  // ---- Closed state --------------------------------------------------------

  it('has no accessibility violations when all dialogs are closed', async () => {
    const { baseElement } = renderDialogs()

    const results = await axe(baseElement)
    expect(results).toHaveNoViolations()
  })
})

// ---------------------------------------------------------------------------
// IdentityActionsKebab
// ---------------------------------------------------------------------------

describe('IdentityActionsKebab', () => {
  const defaultDisconnectedProps = {
    kind: 'disconnected' as const,
    isSelf: true,
    isLocalUser: false,
    providerName: 'GitHub',
    authorizeUrl: '/oidc/authorize?provider_id=gh-1&flow=link',
    onConvert: vi.fn(),
  }

  const defaultConnectedProps = {
    kind: 'connected' as const,
    isLastIdentity: false,
    isDetaching: false,
    onDisconnect: vi.fn(),
  }

  function renderKebab(props: Parameters<typeof IdentityActionsKebab>[0]) {
    return render(<IdentityActionsKebab {...props} />)
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('always renders the kebab toggle', () => {
    renderKebab({ ...defaultDisconnectedProps, isSelf: false })
    expect(screen.getByRole('button', { name: 'Identity actions' })).toBeInTheDocument()
  })

  describe('disconnected row', () => {
    it('shows disabled Connect identity with tooltip when not self', async () => {
      const user = userEvent.setup()
      renderKebab({ ...defaultDisconnectedProps, isSelf: false })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))

      const connectItem = screen.getByRole('menuitem', { name: 'Connect identity' })
      expect(connectItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('calls onConvert when self and local user clicks Connect identity', async () => {
      const user = userEvent.setup()
      const onConvert = vi.fn()
      renderKebab({ ...defaultDisconnectedProps, isSelf: true, isLocalUser: true, onConvert })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      await user.click(screen.getByRole('menuitem', { name: 'Connect identity' }))

      expect(onConvert).toHaveBeenCalledWith({
        name: 'GitHub',
        authorizeUrl: '/oidc/authorize?provider_id=gh-1&flow=link',
      })
    })

    it('does not call onConvert when self and federated user clicks Connect identity', async () => {
      const user = userEvent.setup()
      const onConvert = vi.fn()

      renderKebab({ ...defaultDisconnectedProps, isSelf: true, isLocalUser: false, onConvert })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      await user.click(screen.getByRole('menuitem', { name: 'Connect identity' }))

      // Federated users navigate directly; the local-user conversion dialog is not triggered
      expect(onConvert).not.toHaveBeenCalled()
    })
  })

  describe('connected row', () => {
    it('shows enabled Disconnect when not last identity', async () => {
      const user = userEvent.setup()
      renderKebab(defaultConnectedProps)

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))

      const disconnectItem = screen.getByRole('menuitem', { name: 'Disconnect identity' })
      expect(disconnectItem).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('calls onDisconnect when Disconnect is clicked', async () => {
      const user = userEvent.setup()
      const onDisconnect = vi.fn()
      renderKebab({ ...defaultConnectedProps, onDisconnect })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))
      await user.click(screen.getByRole('menuitem', { name: 'Disconnect identity' }))

      expect(onDisconnect).toHaveBeenCalledTimes(1)
    })

    it('shows disabled Disconnect with tooltip when last identity', async () => {
      const user = userEvent.setup()
      renderKebab({ ...defaultConnectedProps, isLastIdentity: true })

      await user.click(screen.getByRole('button', { name: 'Identity actions' }))

      const disconnectItem = screen.getByRole('menuitem', { name: 'Disconnect identity' })
      expect(disconnectItem).toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('has no accessibility violations (disconnected, admin view)', async () => {
    const { container } = renderKebab({ ...defaultDisconnectedProps, isSelf: false })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations (connected)', async () => {
    const { container } = renderKebab(defaultConnectedProps)
    expect(await axe(container)).toHaveNoViolations()
  })
})
