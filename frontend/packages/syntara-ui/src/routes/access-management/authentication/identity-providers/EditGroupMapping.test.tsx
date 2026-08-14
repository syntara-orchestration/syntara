import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient, usersClient } from '../../../../client'
import { useCanI } from '../../../../hooks/useCanI'
import { AlertProvider } from '../../../../providers/alerts'
import { routerTestState } from '../../../../test/setup'
import { useAllGroups } from '../../../access/useAllGroups'

import { EditGroupMapping } from './EditGroupMapping'

const VALID_PROVIDER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const MOCK_GROUP_ID = 'b1b2c3d4-e5f6-7890-abcd-ef1234567891'
const MOCK_GROUP_ID_2 = 'c1b2c3d4-e5f6-7890-abcd-ef1234567892'
const mockSearchRef = { current: '' }
const mockProviderIdRef = { current: VALID_PROVIDER_ID }

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  usersClient: {
    useQuery: vi.fn(),
  },
  OIDC_AUTHORIZE_PATH: '/api/v1/auth/oidc/authorize',
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockHandleError = vi.fn(() => vi.fn())
vi.mock('../../../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: () => mockHandleError,
}))

vi.mock('../../../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: { useQuery: vi.fn(), useMutation: vi.fn() },
  accessFetchClient: { POST: vi.fn() },
}))

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { routerTestState, MockLink } = await import('../../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => ({ providerId: mockProviderIdRef.current }),
    useRouterState: vi.fn(
      (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
        const state = { location: { pathname: '/', searchStr: mockSearchRef.current } }
        return opts?.select ? opts.select(state) : state
      }
    ),
    useNavigate: () => routerTestState.navigate,
  }
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockNexusGroups = [
  { id: MOCK_GROUP_ID, name: 'admin', description: 'Admins', created_at: '2026-01-01T00:00:00Z' },
  { id: MOCK_GROUP_ID_2, name: 'users', description: 'Users', created_at: '2026-01-02T00:00:00Z' },
]

const mockProvider = {
  id: VALID_PROVIDER_ID,
  name: 'Test Provider',
  enabled: true,
  configuration: {
    issuer_url: 'https://example.com',
    provider_type: 'oidc' as const,
    client_id: 'test-client',
    redirect_uri: 'http://localhost/callback',
    idp_type: 'custom',
  },
}

describe('EditGroupMapping', () => {
  beforeEach(() => {
    mockSearchRef.current = ''
    mockProviderIdRef.current = VALID_PROVIDER_ID
    routerTestState.navigate.mockClear()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
    vi.mocked(useAllGroups).mockReturnValue({
      groups: mockNexusGroups.map((g) => ({
        ...g,
        is_builtin: false,
        updated_at: g.created_at,
      })),
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: mockNexusGroups },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn().mockResolvedValue({ data: { resources: mockNexusGroups } }),
    } as never)

    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: mockProvider,
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  it('renders Add group mapping title when there are no server mappings', async () => {
    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Add group mapping' })).toBeInTheDocument()
    })
  })

  it('renders Edit group mapping title when server mappings exist', async () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: {
        ...mockProvider,
        configuration: {
          ...mockProvider.configuration,
          group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Edit group mapping' })).toBeInTheDocument()
    })
  })

  it('shows Save mapping, Cancel, and Re-discover buttons', async () => {
    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mapping/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-discover groups/i })).toBeInTheDocument()
  })

  it('navigates to group mapping tab on Cancel', async () => {
    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: `/system-administration/authentication/identity-providers/${VALID_PROVIDER_ID}/group-mapping`,
    })
  })

  it('shows validation when saving with incomplete entries', async () => {
    const mockMutate = vi.fn()
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    mockSearchRef.current = '?new=1'
    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
    })

    await user.type(screen.getByRole('textbox', { name: 'IdP group value 1' }), 'admin')
    await user.click(screen.getByRole('button', { name: /save mapping/i }))

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('saves with empty group mappings when all rows are cleared', async () => {
    const mockMutate = vi.fn()
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: {
        ...mockProvider,
        configuration: {
          ...mockProvider.configuration,
          group_jmespath_expression: 'groups[*]',
          group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Remove mapping 1' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Remove mapping 1' }))
    await user.click(screen.getByRole('button', { name: /save mapping/i }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    const patchArgs = mockMutate.mock.calls[0]?.[0] as
      | { body?: { configuration?: { group_mapping_entries?: unknown[] } } }
      | undefined
    expect(patchArgs?.body?.configuration?.group_mapping_entries).toEqual([])
  })

  it('calls patchProvider on save with complete entries', async () => {
    const mockMutate = vi.fn()
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: {
        ...mockProvider,
        configuration: {
          ...mockProvider.configuration,
          group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mapping/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /save mapping/i }))
    expect(mockMutate).toHaveBeenCalled()
  })

  it('navigates to tab after successful save', async () => {
    const mockMutate = vi.fn((_params: unknown, callbacks?: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.()
    })
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: {
        ...mockProvider,
        configuration: {
          ...mockProvider.configuration,
          group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mapping/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /save mapping/i }))

    await waitFor(() => {
      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: `/system-administration/authentication/identity-providers/${VALID_PROVIDER_ID}/group-mapping`,
      })
    })
  })

  it('shows access denied when user lacks identity-provider:update', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Access denied')).toBeInTheDocument()
    })
    expect(screen.getByText(/don't have permission to edit group mapping/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save mapping/i })).not.toBeInTheDocument()
  })

  it('does not show edit form while update permission is checking', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })
    render(<EditGroupMapping />, { wrapper })

    expect(screen.queryByRole('button', { name: /save mapping/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
  })

  it('shows invalid provider empty state for non-UUID id', async () => {
    mockProviderIdRef.current = 'not-a-uuid'
    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invalid identity provider' })).toBeInTheDocument()
    })
  })

  it('shows not found empty state when provider returns 404', async () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { status: 404 } },
      isPending: false,
      refetch: vi.fn(),
    } as never)

    render(<EditGroupMapping />, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Identity provider not found' })).toBeInTheDocument()
    })
  })

  it('navigates back to authentication from not-found empty state', async () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { status: 404 } },
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const user = userEvent.setup()
    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Back to identity providers' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: 'Back to identity providers' }))
    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: '/system-administration/authentication',
    })
  })

  it('shows error state when provider query fails', () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Server error'),
      isPending: false,
      refetch: vi.fn(),
    } as never)

    render(<EditGroupMapping />, { wrapper })
    expect(screen.getAllByText('Error loading identity provider').length).toBeGreaterThan(0)
  })

  it('does not open discover when user lacks update permission', async () => {
    mockSearchRef.current = '?discover=1'
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const mockOpen = vi.fn()
    const originalOpen = globalThis.open
    globalThis.open = mockOpen

    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Access denied')).toBeInTheDocument()
    })
    expect(mockOpen).not.toHaveBeenCalled()

    globalThis.open = originalOpen
  })

  it('opens test sign-in popup when discover query param is set', async () => {
    mockSearchRef.current = '?discover=1'
    const mockOpen = vi.fn()
    const originalOpen = globalThis.open
    globalThis.open = mockOpen

    render(<EditGroupMapping />, { wrapper })

    await waitFor(() => {
      expect(mockOpen).toHaveBeenCalledWith(
        expect.stringContaining(`provider_id=${VALID_PROVIDER_ID}`),
        'test-signin',
        expect.any(String)
      )
    })

    globalThis.open = originalOpen
  })

  describe('Page shell and breadcrumbs', () => {
    it('renders page title with proper hierarchy', async () => {
      render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
      })
    })

    it('includes breadcrumbs navigation', async () => {
      render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        const nav = screen.getByRole('navigation')
        expect(nav).toBeInTheDocument()
      })
    })

    it('renders page with proper heading', async () => {
      render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        const heading = screen.getByRole('heading', { level: 1 })
        expect(heading).toBeInTheDocument()
      })
    })
  })

  describe('Permission checking', () => {
    it('shows empty loading state when checking permission', () => {
      vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: true, isError: false })
      render(<EditGroupMapping />, { wrapper })

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /save mapping/i })).not.toBeInTheDocument()
    })

    it('allows form rendering only after permission check completes', async () => {
      render(<EditGroupMapping />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1, name: /add group mapping/i })).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in access denied state', async () => {
      vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
      const { container } = render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        expect(screen.getByText('Access denied')).toBeInTheDocument()
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in not-found state', async () => {
      vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { response: { status: 404 } },
        isPending: false,
        refetch: vi.fn(),
      } as never)

      const { container } = render(<EditGroupMapping />, { wrapper })
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Identity provider not found' })).toBeInTheDocument()
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
