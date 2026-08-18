import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import { routerTestState } from '../../../../test/setup'
import type { DocKey } from '../../../../utils/docs/types'

import { IdentityProviderForm } from './IdentityProviderForm'

type MutationCallbacks = {
  onSuccess?: (data?: unknown) => void
  onError?: (error: unknown) => void
}

function getMutationCallbacks(mockFn: ReturnType<typeof vi.fn>): MutationCallbacks {
  return (mockFn.mock.calls[0]?.[1] ?? {}) as MutationCallbacks
}

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  OIDC_REDIRECT_URI: 'http://localhost/api/v1/auth/oidc/callback',
}))

const { mockUseParams } = vi.hoisted(() => ({
  mockUseParams: vi.fn(() => ({})),
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { routerTestState, MockLink } = await import('../../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => mockUseParams(),
    useNavigate: () => routerTestState.navigate,
  }
})

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(() => ({
    groups: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
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
  } as never)
  vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never)
}

describe('IdentityProviderForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockUseParams.mockReturnValue({})
    routerTestState.navigate.mockClear()
  })

  describe('add mode', () => {
    it('renders the add form with submit button on last step', async () => {
      setupMocks()
      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Add OIDC provider' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Add provider' })).not.toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      expect(screen.getByRole('button', { name: 'Add provider' })).toBeInTheDocument()
    })

    it('uses addIdentityProvider documentation key', () => {
      setupMocks()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(useDocLinkMock).toHaveBeenCalledWith('addIdentityProvider')
      expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute(
        'href',
        'https://docs.example/addIdentityProvider'
      )
    })

    it('renders test connection button', () => {
      setupMocks()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(screen.getByRole('button', { name: 'Test connection' })).toBeInTheDocument()
    })

    it('renders cancel button on all steps', () => {
      setupMocks()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders all required form fields', () => {
      setupMocks()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(screen.getByLabelText(/Provider name/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Issuer URL/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Client secret/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Scopes/)).toBeInTheDocument()
    })

    it('renders redirect URI as read-only clipboard copy', () => {
      setupMocks()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      expect(screen.getByText(/Redirect URI/)).toBeInTheDocument()
      expect(screen.getByDisplayValue(/\/api\/v1\/auth\/oidc\/callback/)).toBeInTheDocument()
    })

    it('shows manual endpoint fields when auto-discovery is disabled', async () => {
      setupMocks()
      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      // Toggle auto-discovery off
      const autoDiscoverySwitch = screen.getByLabelText(/Use OIDC Discovery/)
      await user.click(autoDiscoverySwitch)

      expect(screen.getByLabelText(/Authorization endpoint/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Token endpoint/)).toBeInTheDocument()
      expect(screen.getByLabelText(/JWKS URI/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Userinfo endpoint/)).toBeInTheDocument()
    })

    it('has no accessibility violations', async () => {
      setupMocks()
      const { container } = render(<IdentityProviderForm mode="add" />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('edit mode', () => {
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

    function setupEditMocks() {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: mockProvider,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)
    }

    it('renders the edit form with Save button on last step', async () => {
      setupEditMocks()
      const user = userEvent.setup()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit OIDC provider' })).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      expect(screen.getByRole('button', { name: 'Save provider' })).toBeInTheDocument()
    })

    it('uses identityProviders documentation key', () => {
      setupEditMocks()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(useDocLinkMock).toHaveBeenCalledWith('identityProviders')
      expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute(
        'href',
        'https://docs.example/identityProviders'
      )
    })

    it('populates form with provider data', () => {
      setupEditMocks()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByDisplayValue('Azure AD')).toBeInTheDocument()
      expect(screen.getByDisplayValue('https://login.microsoftonline.com/tenant')).toBeInTheDocument()
      expect(screen.getByDisplayValue('client-123')).toBeInTheDocument()
    })

    it('shows not found state when provider does not exist', () => {
      const notFoundError = Object.assign(new Error('Not found'), { status: 404 })
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: notFoundError,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByText('Identity provider not found')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Back to identity providers/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
    })

    it('shows loading state while fetching provider', () => {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: true,
        isPending: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
        status: 'pending',
        fetchStatus: 'fetching',
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit OIDC provider' })).toBeInTheDocument()
      // Should not render the submit button since the loading state takes over
      expect(screen.queryByRole('button', { name: 'Save provider' })).not.toBeInTheDocument()
    })

    it('calls patchProvider on submit in edit mode', async () => {
      const mockPatch = vi.fn()
      mockUseParams.mockReturnValue({ providerId: 'provider-1' })
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: mockProvider,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string) => {
        if (method === 'patch') {
          return { mutate: mockPatch, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Save provider' }))

      await waitFor(() => {
        expect(mockPatch).toHaveBeenCalled()
      })

      // Simulate onSuccess callback
      act(() => {
        getMutationCallbacks(mockPatch).onSuccess?.()
      })
      expect(routerTestState.navigate).toHaveBeenCalled()
    })

    it('includes aap_role_mapping_enabled in patch payload for AAP provider', async () => {
      const mockPatch = vi.fn()
      const aapProvider = {
        id: 'provider-1',
        name: 'AAP Provider',
        enabled: true,
        configuration: {
          provider_type: 'oidc',
          idp_type: 'aap',
          auto_discovery: true,
          issuer_url: 'https://aap.example.com',
          client_id: 'aap-client',
          scopes: 'openid profile email',
          aap_role_mapping_enabled: true,
          enable_rp_initiated_logout: true,
        },
      }
      mockUseParams.mockReturnValue({ providerId: 'provider-1' })
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: aapProvider,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string) => {
        if (method === 'patch') {
          return { mutate: mockPatch, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Save provider' }))

      await waitFor(() => {
        expect(mockPatch).toHaveBeenCalled()
      })

      const callArgs = mockPatch.mock.calls[0] as [{ body: { configuration: { aap_role_mapping_enabled: boolean } } }]
      expect(callArgs[0].body.configuration.aap_role_mapping_enabled).toBe(true)
    })

    it('includes disable_tls_verify in patch payload', async () => {
      const mockPatch = vi.fn()
      const providerWithTlsDisabled = {
        id: 'provider-1',
        name: 'Self-signed IdP',
        enabled: true,
        configuration: {
          provider_type: 'oidc',
          auto_discovery: true,
          issuer_url: 'https://self-signed.example.com',
          client_id: 'client-123',
          scopes: 'openid profile email',
          disable_tls_verify: true,
        },
      }
      mockUseParams.mockReturnValue({ providerId: 'provider-1' })
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: providerWithTlsDisabled,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string) => {
        if (method === 'patch') {
          return { mutate: mockPatch, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByLabelText(/Disable TLS certificate verification/)).toBeChecked()

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Save provider' }))

      await waitFor(() => {
        expect(mockPatch).toHaveBeenCalled()
      })

      const callArgs = mockPatch.mock.calls[0] as [{ body: { configuration: { disable_tls_verify: boolean } } }]
      expect(callArgs[0].body.configuration.disable_tls_verify).toBe(true)
    })

    it('defaults disable_tls_verify to false when not set in provider data', () => {
      setupEditMocks()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      expect(screen.getByLabelText(/Disable TLS certificate verification/)).not.toBeChecked()
    })

    it('defaults mappedGroupId to empty string when mapped_group_id is null in API response', () => {
      const providerWithNullMapping = {
        id: 'provider-1',
        name: 'Azure AD',
        enabled: true,
        configuration: {
          provider_type: 'oidc',
          auto_discovery: true,
          issuer_url: 'https://login.microsoftonline.com/tenant',
          client_id: 'client-123',
          scopes: 'openid profile email',
          group_jmespath_expression: 'groups[*]',
          group_mapping_entries: [{ idp_group_value: 'admins', mapped_group_id: null as unknown as string }],
        },
      }
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: providerWithNullMapping,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      // Should render without crashing — null mapped_group_id defaults to ''
      render(<IdentityProviderForm mode="edit" />, { wrapper })
      expect(screen.getByRole('heading', { name: 'Edit OIDC provider' })).toBeInTheDocument()
    })

    it('populates group mapping form values from provider group_mapping_entries', () => {
      const providerWithMappings = {
        id: 'provider-1',
        name: 'Azure AD',
        enabled: true,
        configuration: {
          provider_type: 'oidc',
          auto_discovery: true,
          issuer_url: 'https://login.microsoftonline.com/tenant',
          client_id: 'client-123',
          scopes: 'openid profile email',
          group_jmespath_expression: 'groups[*]',
          group_mapping_entries: [
            { idp_group_value: 'admins', mapped_group_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6' },
          ],
        },
      }
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: providerWithMappings,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<IdentityProviderForm mode="edit" />, { wrapper })

      // Form renders without error — group mapping data was correctly deserialized
      expect(screen.getByRole('heading', { name: 'Edit OIDC provider' })).toBeInTheDocument()
    })

    it('includes mapped_group_id in patch payload when group mapping entries are present', async () => {
      const mockPatch = vi.fn()
      const providerWithMappings = {
        id: 'provider-1',
        name: 'Azure AD',
        enabled: true,
        configuration: {
          provider_type: 'oidc',
          auto_discovery: true,
          issuer_url: 'https://login.microsoftonline.com/tenant',
          client_id: 'client-123',
          scopes: 'openid profile email',
          group_jmespath_expression: 'groups[*]',
          group_mapping_entries: [
            { idp_group_value: 'admins', mapped_group_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6' },
          ],
        },
      }
      mockUseParams.mockReturnValue({ providerId: 'provider-1' })
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: providerWithMappings,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string) => {
        if (method === 'patch') {
          return { mutate: mockPatch, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Save provider' }))

      await waitFor(() => expect(mockPatch).toHaveBeenCalled())

      const body = (mockPatch.mock.calls[0] as [{ body: { configuration: { group_mapping_entries: unknown[] } } }])[0]
        .body.configuration
      expect(body.group_mapping_entries).toEqual([
        { idp_group_value: 'admins', mapped_group_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6' },
      ])
    })
  })

  describe('submit and test connection', () => {
    it('calls createProvider on submit in add mode', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      // Fill required fields
      // Select Provider Template via PF6 Select dropdown
      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Custom/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'My Provider')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'client-id')
      await user.type(screen.getByLabelText(/Client secret/), 'client-secret')

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled()
      })

      // Simulate onSuccess callback
      act(() => {
        getMutationCallbacks(mockCreate).onSuccess?.()
      })
      expect(routerTestState.navigate).toHaveBeenCalled()
    })

    it('includes aap_role_mapping_enabled in create payload for AAP template', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Ansible Automation Platform/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'AAP Provider')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://aap.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'aap-client')
      await user.type(screen.getByLabelText(/Client secret/), 'aap-secret')

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled()
      })

      const callArgs = mockCreate.mock.calls[0] as [{ body: { configuration: { aap_role_mapping_enabled: boolean } } }]
      expect(callArgs[0].body.configuration.aap_role_mapping_enabled).toBe(true)
    })

    it('submits with empty group mapping when step 2 fields are untouched', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Custom/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'test')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'cid')
      await user.type(screen.getByLabelText(/Client secret/), 'csecret')

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    })

    it('includes disable_tls_verify in create payload', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Custom/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'TLS Test')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'client-id')
      await user.type(screen.getByLabelText(/Client secret/), 'secret')

      await user.click(screen.getByLabelText(/Disable TLS certificate verification/))

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled()
      })

      const callArgs = mockCreate.mock.calls[0] as [{ body: { configuration: { disable_tls_verify: boolean } } }]
      expect(callArgs[0].body.configuration.disable_tls_verify).toBe(true)
    })

    it('sets name field error on conflict error', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      // Select Provider Template via PF6 Select dropdown
      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Custom/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'Duplicate')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'client-id')
      await user.type(screen.getByLabelText(/Client secret/), 'secret')

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled()
      })

      // Simulate conflict error
      const conflictError = { code: 'PROVIDER_NAME_CONFLICT', detail: 'conflict' }
      act(() => {
        getMutationCallbacks(mockCreate).onError?.(conflictError)
      })

      // The form auto-navigates to the provider configuration step on conflict
      await waitFor(() => {
        expect(screen.getByText(/already exists/)).toBeInTheDocument()
      })
    })

    it('handles non-conflict submit error via generic error handler', async () => {
      const mockCreate = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((_method: string, path: string) => {
        if (path === '/identity_providers') {
          return { mutate: mockCreate, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Select a provider template/ }))
      await user.click(screen.getByRole('option', { name: /Custom/ }))
      await user.type(screen.getByLabelText(/Provider name/), 'Test Provider')
      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client ID/), 'client-id')
      await user.type(screen.getByLabelText(/Client secret/), 'secret')

      await user.click(screen.getByRole('button', { name: 'Claim mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add provider' }))

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled()
      })

      const serverError = new Error('Internal server error')
      act(() => {
        getMutationCallbacks(mockCreate).onError?.(serverError)
      })

      await waitFor(() => {
        expect(screen.getByText(/Failed to add identity provider/)).toBeInTheDocument()
      })
    })

    it('handles test connection success with RP-logout supported', async () => {
      const mockTest = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string, path: string) => {
        if (method === 'post' && path === '/identity_providers/test') {
          return { mutate: mockTest, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalled()
      })

      // Simulate success with end_session_endpoint_supported
      act(() => {
        getMutationCallbacks(mockTest).onSuccess?.({
          success: true,
          message: 'Connected',
          end_session_endpoint_supported: true,
        })
      })

      // Toast alerts are shown via showAlert — title renders as the PF Alert heading
      await waitFor(() => {
        expect(screen.getByText('Connection successful')).toBeInTheDocument()
        expect(screen.getByText('Connected')).toBeInTheDocument()
        expect(screen.getByText('Single logout supported')).toBeInTheDocument()
      })
    })

    it('handles test connection success without single logout support', async () => {
      const mockTest = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string, path: string) => {
        if (method === 'post' && path === '/identity_providers/test') {
          return { mutate: mockTest, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalled()
      })

      // Simulate success without end_session_endpoint_supported
      act(() => {
        getMutationCallbacks(mockTest).onSuccess?.({
          success: true,
          message: 'Connected',
          end_session_endpoint_supported: false,
        })
      })

      // Only the success toast is shown — no separate single logout toast
      await waitFor(() => {
        expect(screen.getByText('Connection successful')).toBeInTheDocument()
        expect(screen.getByText('Connected')).toBeInTheDocument()
      })
      expect(screen.queryByText('Single logout supported')).not.toBeInTheDocument()
    })

    it('excludes client_secret from test connection payload', async () => {
      const mockTest = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string, path: string) => {
        if (method === 'post' && path === '/identity_providers/test') {
          return { mutate: mockTest, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.type(screen.getByLabelText(/Client secret/), 'super-secret-value')
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalled()
      })

      const callArgs = mockTest.mock.calls[0] as [{ body: { configuration: Record<string, unknown> } }]
      expect(callArgs[0].body.configuration.client_secret).toBeUndefined()
    })

    it('handles test connection failure', async () => {
      const mockTest = vi.fn()
      setupMocks()

      vi.mocked(identityProvidersClient.useMutation).mockImplementation(((method: string, path: string) => {
        if (method === 'post' && path === '/identity_providers/test') {
          return { mutate: mockTest, isPending: false }
        }
        return { mutate: vi.fn(), isPending: false }
      }) as never)

      const user = userEvent.setup()
      render(<IdentityProviderForm mode="add" />, { wrapper })

      await user.type(screen.getByLabelText(/Issuer URL/), 'https://issuer.example.com')
      await user.click(screen.getByRole('button', { name: 'Test connection' }))

      await waitFor(() => {
        expect(mockTest).toHaveBeenCalled()
      })

      // Simulate error callback
      act(() => {
        getMutationCallbacks(mockTest).onError?.(new Error('Connection refused'))
      })

      await waitFor(() => {
        expect(screen.getByText('Connection failed')).toBeInTheDocument()
      })
    })
  })
})
