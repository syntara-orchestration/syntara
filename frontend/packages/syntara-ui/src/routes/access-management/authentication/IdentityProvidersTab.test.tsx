import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { adminClient, identityProvidersClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'

import { IdentityProvidersTab, type IdentityProvidersHeaderToolbarState } from './IdentityProvidersTab'

type MutationCallbacks = {
  onSuccess?: () => void
  onError?: (error: unknown) => void
  onSettled?: () => void
}

function getMutationCallbacks(mockFn: ReturnType<typeof vi.fn>): MutationCallbacks {
  return (mockFn.mock.calls[0]?.[1] ?? {}) as MutationCallbacks
}

vi.mock('../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  adminClient: {
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

let currentSearchParams = new URLSearchParams()

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [currentSearchParams, vi.fn()],
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

function setupProviders(providers = [mockProvider]) {
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

describe('IdentityProvidersTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentSearchParams = new URLSearchParams()
    vi.mocked(adminClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  describe('loading state', () => {
    it('renders loading state while data is being fetched', () => {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
        isPending: true,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByRole('progressbar', { name: /Loading/ })).toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('renders error state when query fails', () => {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error('Network error'),
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Error loading identity providers' })).toBeInTheDocument()
    })

    it('shows retry button and retries on click for retryable errors', async () => {
      const mockRefetch = vi.fn().mockResolvedValue({})
      const user = userEvent.setup()
      const retryableError = Object.assign(new Error('Server error'), { retryable: true })

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: retryableError,
        isPending: false,
        refetch: mockRefetch,
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      const retryButton = screen.getByRole('button', { name: /retry/i })
      await user.click(retryButton)

      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  describe('empty state', () => {
    it('renders empty state when no providers exist', () => {
      setupEmptyProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByText('No identity providers configured yet')).toBeInTheDocument()
      expect(screen.getByText(/Configure an external identity provider to enable single sign-on/)).toBeInTheDocument()
    })

    it('renders add button in empty state', () => {
      setupEmptyProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByRole('button', { name: /Add OIDC provider/ })).toBeInTheDocument()
    })

    it('navigates to add provider page when add button clicked', async () => {
      setupEmptyProviders()
      const user = userEvent.setup()
      render(<IdentityProvidersTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Add OIDC provider/ }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/add',
      })
    })

    it('opens AAP setup modal when Add Ansible Automation Platform button is clicked', async () => {
      setupEmptyProviders()
      const user = userEvent.setup()
      render(<IdentityProvidersTab />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Add Ansible Automation Platform/ }))

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('has no accessibility violations in empty state', async () => {
      setupEmptyProviders()
      const { container } = render(<IdentityProvidersTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('with providers', () => {
    it('renders provider table with data', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByText('Azure AD')).toBeInTheDocument()
      expect(screen.getByText('https://login.microsoftonline.com/tenant')).toBeInTheDocument()
      expect(screen.getByText('client-123')).toBeInTheDocument()
    })

    it('renders table column headers', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByRole('columnheader', { name: /Name/ })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /State/ })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Issuer URL/ })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Client ID/ })).toBeInTheDocument()
    })

    it('does not put create actions in the list panel toolbar', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.queryByRole('button', { name: /Add OIDC provider/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Add Ansible Automation Platform/ })).not.toBeInTheDocument()
    })

    it('reports header toolbar state for page header actions', () => {
      const onHeaderToolbarStateChange = vi.fn()
      setupProviders()
      render(<IdentityProvidersTab onHeaderToolbarStateChange={onHeaderToolbarStateChange} />, { wrapper })

      expect(onHeaderToolbarStateChange).toHaveBeenCalledWith(
        expect.objectContaining({
          showToolbar: true,
          showAapButton: true,
          openAapSetup: expect.any(Function) as unknown,
        })
      )
    })

    it('opens AAP setup modal from header toolbar callback', () => {
      let openAapSetup: (() => void) | undefined
      const onHeaderToolbarStateChange = vi.fn((state: IdentityProvidersHeaderToolbarState | null) => {
        openAapSetup = state?.openAapSetup
      })
      setupProviders()
      render(<IdentityProvidersTab onHeaderToolbarStateChange={onHeaderToolbarStateChange} />, { wrapper })

      expect(openAapSetup).toBeTypeOf('function')
      act(() => {
        openAapSetup?.()
      })

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('hides AAP action in header toolbar state when AAP provider exists', () => {
      const onHeaderToolbarStateChange = vi.fn()
      const aapProvider = {
        ...mockProvider,
        id: 'aap-1',
        name: 'AAP',
        configuration: { ...mockProvider.configuration, idp_type: 'aap' },
      }
      setupProviders([aapProvider])
      render(<IdentityProvidersTab onHeaderToolbarStateChange={onHeaderToolbarStateChange} />, { wrapper })

      expect(onHeaderToolbarStateChange).toHaveBeenCalledWith(
        expect.objectContaining({
          showToolbar: true,
          showAapButton: false,
        })
      )
    })

    it('shows provider count in footer', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      // PF Pagination renders item count display
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
    })

    it('renders disabled provider with unchecked switch', () => {
      setupProviders([{ ...mockProvider, enabled: false }])
      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      expect(toggle).not.toBeChecked()
    })

    it('has no accessibility violations with providers', async () => {
      setupProviders()
      const { container } = render(<IdentityProvidersTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('shows total count when more providers exist than displayed', () => {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 5 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      // PF Pagination renders item count display with total
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('renders provider name as a navigational link to the provider detail page', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const link = screen.getByRole('link', { name: 'Azure AD' })
      expect(link).toHaveAttribute('href', '/system-administration/authentication/identity-providers/provider-1')
    })

    it('opens delete confirmation dialog when delete action is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      // Open the actions kebab menu
      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)

      // Click delete
      await user.click(screen.getByText('Delete'))

      // Delete dialog should appear
      expect(screen.getByText('Delete identity provider?')).toBeInTheDocument()
      expect(screen.getByText(/will be deleted. This cannot be undone/)).toBeInTheDocument()
    })

    it('shows delete consequences in confirmation dialog', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Delete'))

      expect(screen.getByText(/Remove all user identities linked to this provider/)).toBeInTheDocument()
      expect(screen.getByText(/Revoke active sessions authenticated via this provider/)).toBeInTheDocument()
      expect(screen.getByText(/Prevent users from signing in with this provider/)).toBeInTheDocument()
      expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument()
    })

    it('closes delete dialog when cancel is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      // Open delete dialog
      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Delete'))

      // Cancel
      await user.click(screen.getByText('Cancel'))

      expect(screen.queryByText('Delete identity provider?')).not.toBeInTheDocument()
    })

    it('calls delete mutation when confirmed', async () => {
      const mockDeleteMutate = vi.fn()
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers/{provider_id}' && _method === 'delete') {
          return { mutate: mockDeleteMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      // Open delete dialog
      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Delete'))

      // Check the acknowledgement checkbox before clicking Delete
      const dialog = screen.getByRole('dialog')
      await user.click(within(dialog).getByRole('checkbox'))

      // Confirm delete — target the button inside the modal dialog
      await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

      expect(mockDeleteMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          params: { path: { provider_id: 'provider-1' } },
        }),
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
          onSettled: expect.any(Function) as unknown,
        })
      )
    })

    it('closes dialog and refetches after successful deletion', async () => {
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn().mockResolvedValue({})
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: mockRefetch,
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers/{provider_id}' && _method === 'delete') {
          return { mutate: mockDeleteMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      // Open delete dialog and confirm
      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Delete'))
      const dialog = screen.getByRole('dialog')
      // Check the acknowledgement checkbox before clicking Delete
      await user.click(within(dialog).getByRole('checkbox'))
      await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

      // Simulate onSuccess and onSettled callbacks from useDeleteAction
      act(() => {
        getMutationCallbacks(mockDeleteMutate).onSuccess?.()
        getMutationCallbacks(mockDeleteMutate).onSettled?.()
      })

      expect(mockRefetch).toHaveBeenCalled()
    })

    it('navigates to edit page when edit action is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Edit provider'))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/provider-1/edit',
      })
    })

    it('navigates to group mapping page when edit mapping action is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByRole('menuitem', { name: /edit group mapping/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/provider-1/group-mapping/edit',
      })
    })

    it('opens revoke confirmation dialog when revoke action is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Revoke tokens'))

      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText('Revoke identity provider tokens?')).toBeInTheDocument()
      expect(within(dialog).getByText(/will be revoked/)).toBeInTheDocument()
      expect(within(dialog).getByText('Azure AD')).toBeInTheDocument()
    })

    it('closes revoke dialog when cancel is clicked', async () => {
      const user = userEvent.setup()
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Revoke tokens'))

      await user.click(screen.getByText('Cancel'))

      expect(screen.queryByText('Revoke identity provider tokens?')).not.toBeInTheDocument()
    })

    it('calls revoke mutation when confirmed', async () => {
      const mockRevokeMutate = vi.fn()
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
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
        mutate: mockRevokeMutate,
        isPending: false,
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      const actionsButton = screen.getByRole('button', { name: /Kebab toggle/ })
      await user.click(actionsButton)
      await user.click(screen.getByText('Revoke tokens'))

      const dialog = screen.getByRole('dialog')
      await user.click(within(dialog).getByRole('button', { name: 'Revoke tokens' }))

      expect(mockRevokeMutate).toHaveBeenCalled()
      const callArgs = mockRevokeMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({ params: { path: { idp_name: 'Azure AD' } } })
    })
  })

  describe('toggle enable/disable', () => {
    it('opens disable confirmation dialog when toggling an enabled provider', async () => {
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)

      expect(screen.getByText('Disable identity provider?')).toBeInTheDocument()
      expect(screen.getByText(/You are about to disable the identity provider/)).toBeInTheDocument()
    })

    it('calls patch mutation to disable after confirming dialog', async () => {
      const mockPatchMutate = vi.fn()
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)

      await user.click(screen.getByRole('button', { name: 'Disable' }))

      expect(mockPatchMutate).toHaveBeenCalledWith(
        { params: { path: { provider_id: 'provider-1' } }, body: { enabled: false } },
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('calls patch mutation to enable a disabled provider', async () => {
      const mockPatchMutate = vi.fn()
      const disabledProvider = { ...mockProvider, enabled: false }
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [disabledProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)

      expect(mockPatchMutate).toHaveBeenCalledWith(
        { params: { path: { provider_id: 'provider-1' } }, body: { enabled: true } },
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('refetches after enabling a provider', async () => {
      const mockPatchMutate = vi.fn()
      const mockRefetch = vi.fn().mockResolvedValue({})
      const disabledProvider = { ...mockProvider, enabled: false }
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [disabledProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: mockRefetch,
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)

      // Simulate onSuccess callback
      act(() => {
        getMutationCallbacks(mockPatchMutate).onSuccess?.()
      })

      expect(mockRefetch).toHaveBeenCalled()
    })

    it('refetches after disabling a provider', async () => {
      const mockPatchMutate = vi.fn()
      const mockRefetch = vi.fn().mockResolvedValue({})
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: mockRefetch,
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)
      await user.click(screen.getByRole('button', { name: 'Disable' }))

      act(() => {
        getMutationCallbacks(mockPatchMutate).onSuccess?.()
      })

      expect(mockRefetch).toHaveBeenCalled()
    })

    it('shows error alert when disable fails after confirming dialog', async () => {
      const mockPatchMutate = vi.fn()
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)
      await user.click(screen.getByRole('button', { name: 'Disable' }))

      act(() => {
        getMutationCallbacks(mockPatchMutate).onError?.(new Error('Server error'))
      })

      expect(screen.getByText('Failed to disable identity provider')).toBeInTheDocument()
    })

    it('does not call patch when cancel is clicked in disable dialog', async () => {
      const mockPatchMutate = vi.fn()
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [mockProvider], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(mockPatchMutate).not.toHaveBeenCalled()
    })

    it('does not call patch when provider has no id', async () => {
      const mockPatchMutate = vi.fn()
      const providerWithoutId = { ...mockProvider, id: undefined }
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [providerWithoutId], total: 1 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (_method === 'patch' && path === '/identity_providers/{provider_id}') {
          return { mutate: mockPatchMutate }
        }
        return { mutate: vi.fn() }
      }) as never)

      render(<IdentityProvidersTab />, { wrapper })

      const toggle = screen.getByRole('switch', { name: /Toggle Azure AD/i })
      await user.click(toggle)

      expect(mockPatchMutate).not.toHaveBeenCalled()
    })
  })

  describe('provider without id', () => {
    it('renders provider name as plain text when provider has no id', () => {
      const providerWithoutId = { ...mockProvider, id: undefined }
      setupProviders([providerWithoutId] as unknown as (typeof mockProvider)[])
      render(<IdentityProvidersTab />, { wrapper })

      expect(screen.getByText('Azure AD')).toBeInTheDocument()
      // Should not be a link/button
      expect(screen.queryByRole('button', { name: 'Azure AD' })).not.toBeInTheDocument()
    })
  })

  describe('filter empty state', () => {
    it('shows filter empty state when no results match active filters', () => {
      currentSearchParams = new URLSearchParams({ 'name[contains]': 'nonexistent' })

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [], total: 0 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      // Should show the filter empty state, not the "no providers" empty state
      expect(screen.queryByText('No identity providers configured yet')).not.toBeInTheDocument()
      expect(screen.getByText(/No results found/i)).toBeInTheDocument()
    })

    it('renders clear all filters button in filter empty state', async () => {
      currentSearchParams = new URLSearchParams({ 'name[contains]': 'nonexistent' })
      const user = userEvent.setup()

      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: { resources: [], total: 0 },
        isLoading: false,
        isError: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
      } as never)

      render(<IdentityProvidersTab />, { wrapper })

      const clearButtons = screen.getAllByRole('button', { name: /Clear all filters/i })
      expect(clearButtons.length).toBeGreaterThan(0)
      // Click the clear button in the empty state area
      await user.click(clearButtons[clearButtons.length - 1])
    })
  })

  describe('uses correct API paths', () => {
    it('queries identity_providers with full path', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(identityProvidersClient.useQuery).toHaveBeenCalledWith('get', '/identity_providers', expect.any(Object))
    })

    it('sets up delete mutation with full path', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(identityProvidersClient.useMutation).toHaveBeenCalledWith('delete', '/identity_providers/{provider_id}')
    })

    it('sets up patch mutation with full path', () => {
      setupProviders()
      render(<IdentityProvidersTab />, { wrapper })

      expect(identityProvidersClient.useMutation).toHaveBeenCalledWith('patch', '/identity_providers/{provider_id}')
    })
  })

  it('handles stable re-render without data changes', () => {
    setupProviders()
    const { rerender } = render(<IdentityProvidersTab />, { wrapper })
    rerender(<IdentityProvidersTab />)
    expect(screen.getByText('Azure AD')).toBeInTheDocument()
  })
})
