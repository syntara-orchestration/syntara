import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createRef } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { identityProvidersClient, usersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import type { DocKey } from '../../../../utils/docs/types'
import { useAllGroups } from '../../../access/useAllGroups'

import { GroupMappingFormEditor } from './GroupMappingFormEditor'
import type { UseGroupMappingFormMetadataResult } from './useGroupMappingForm'

const VALID_PROVIDER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

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

vi.mock('../../../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: () => vi.fn(() => vi.fn()),
}))

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

vi.mock('./useTestSignIn', () => ({
  useTestSignIn: () => ({
    openTestSignIn: vi.fn(),
    isListening: false,
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
  id: VALID_PROVIDER_ID,
  name: 'Test Provider',
  enabled: true,
  created_by: 'admin',
  configuration: {
    issuer_url: 'https://example.com',
    provider_type: 'oidc' as const,
    client_id: 'test-client',
    redirect_uri: 'http://localhost/callback',
    idp_type: 'custom',
  },
}

function buildMetadata(overrides: Partial<UseGroupMappingFormMetadataResult> = {}): UseGroupMappingFormMetadataResult {
  return {
    pageTitle: 'Add group mapping',
    breadcrumbs: [{ label: 'Identity providers', href: '/system-administration/authentication' }],
    isValidId: true,
    isNotFound: false,
    queryState: null,
    isReady: true,
    isAddFlow: true,
    openDiscoverOnMount: false,
    providerId: VALID_PROVIDER_ID,
    providerData: mockProvider,
    config: mockProvider.configuration,
    defaultExpression: 'groups[*]',
    idpType: 'custom',
    groupMappingConfig: null,
    ...overrides,
  }
}

describe('GroupMappingFormEditor', () => {
  beforeEach(() => {
    useDocLinkMock.mockClear()
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  it('uses identityProviderMapping documentation key', async () => {
    render(<GroupMappingFormEditor metadata={buildMetadata()} openTestSignInRef={createRef()} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Add group mapping' })).toBeInTheDocument()
    })
    expect(useDocLinkMock).toHaveBeenCalledWith('identityProviderMapping')
    expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute(
      'href',
      'https://docs.example/identityProviderMapping'
    )
  })

  it('disables Save mapping while the patch mutation is pending', async () => {
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
    } as never)

    render(<GroupMappingFormEditor metadata={buildMetadata()} openTestSignInRef={createRef()} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mapping/i })).toBeDisabled()
    })
  })

  it('renders save and cancel actions with the mapping editor', async () => {
    const openTestSignInRef = createRef<(() => void) | null>()

    render(<GroupMappingFormEditor metadata={buildMetadata()} openTestSignInRef={openTestSignInRef} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mapping/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
    expect(openTestSignInRef.current).toBeTypeOf('function')
  })

  it('returns null when provider metadata is incomplete', () => {
    const { container } = render(
      <GroupMappingFormEditor
        metadata={buildMetadata({ providerId: undefined, config: undefined, isReady: false })}
        openTestSignInRef={createRef()}
      />,
      { wrapper }
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <GroupMappingFormEditor metadata={buildMetadata()} openTestSignInRef={createRef()} />,
      { wrapper }
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Add group mapping' })).toBeInTheDocument()
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
