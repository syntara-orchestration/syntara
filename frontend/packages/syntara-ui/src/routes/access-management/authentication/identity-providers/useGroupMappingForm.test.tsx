import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { identityProvidersClient } from '../../../../client'
import { routerTestState } from '../../../../test/setup'
import { useAllGroups } from '../../../access/useAllGroups'

import { useGroupMappingEditForm, useGroupMappingFormMetadata } from './useGroupMappingForm'

const VALID_PROVIDER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const MOCK_GROUP_ID = 'b1b2c3d4-e5f6-7890-abcd-ef1234567891'
const MOCK_NEW_GROUP_ID = 'd1b2c3d4-e5f6-7890-abcd-ef1234567893'

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  OIDC_AUTHORIZE_PATH: '/api/v1/auth/oidc/authorize',
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockHandleError = vi.fn(() => vi.fn())
vi.mock('../../../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: () => mockHandleError,
}))

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

const testSignInCallbacks: {
  onResult?: (claims: Record<string, unknown>) => void
  onError?: () => void
} = {}

vi.mock('./useTestSignIn', () => ({
  useTestSignIn: (options: { onResult?: (claims: Record<string, unknown>) => void; onError?: () => void }) => {
    testSignInCallbacks.onResult = options.onResult
    testSignInCallbacks.onError = options.onError
    return {
      openTestSignIn: vi.fn(),
      isListening: false,
    }
  },
}))

const mockShowAlert = vi.fn()
const mockShowSuccess = vi.fn()
vi.mock('../../../../providers/alerts', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert, showSuccess: mockShowSuccess }),
}))

vi.mock('../../../../hooks/useApiErrorAlert', () => ({
  useApiErrorAlert: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

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

describe('useGroupMappingFormMetadata', () => {
  beforeEach(() => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: mockProvider,
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)
  })

  it('reports invalid provider id', () => {
    const { result } = renderHook(() => useGroupMappingFormMetadata('not-a-uuid', ''), { wrapper })
    expect(result.current.isValidId).toBe(false)
  })

  it('parses add flow and discover search params', () => {
    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, '?new=1&discover=1'), {
      wrapper,
    })
    expect(result.current.isAddFlow).toBe(true)
    expect(result.current.openDiscoverOnMount).toBe(true)
  })

  it('uses Add group mapping title when there are no server mappings', async () => {
    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, '?new=1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.pageTitle).toBe('Add group mapping')
  })

  it('uses Edit group mapping title when server mappings exist', async () => {
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

    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, ''), { wrapper })

    await waitFor(() => {
      expect(result.current.pageTitle).toBe('Edit group mapping')
    })
  })

  it('reports not found when provider query returns 404', () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { status: 404 } },
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, ''), { wrapper })
    expect(result.current.isNotFound).toBe(true)
  })

  it('uses placeholder breadcrumb label while provider name is loading', () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      isPending: true,
      refetch: vi.fn(),
    } as never)

    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, ''), { wrapper })
    expect(result.current.breadcrumbs.some((item) => item.label === 'Identity provider')).toBe(true)
  })

  it('uses provider name in breadcrumbs when loaded', async () => {
    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, ''), { wrapper })

    await waitFor(() => {
      expect(result.current.breadcrumbs.some((item) => item.label === 'Test Provider')).toBe(true)
    })
  })

  it('returns null default expression for unknown provider types', async () => {
    vi.mocked(identityProvidersClient.useQuery).mockReturnValue({
      data: {
        ...mockProvider,
        configuration: {
          ...mockProvider.configuration,
          idp_type: 'unknown-provider',
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    const { result } = renderHook(() => useGroupMappingFormMetadata(VALID_PROVIDER_ID, ''), { wrapper })

    await waitFor(() => {
      expect(result.current.defaultExpression).toBeNull()
    })
  })
})

describe('useGroupMappingEditForm', () => {
  beforeEach(() => {
    testSignInCallbacks.onResult = undefined
    testSignInCallbacks.onError = undefined
    routerTestState.navigate.mockClear()
    mockShowAlert.mockClear()
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [
        { id: MOCK_GROUP_ID, name: 'admin', is_builtin: false, created_at: '2026-01-01', updated_at: '2026-01-01' },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
  })

  it('initializes one blank entry when provider has no mappings', async () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.panel.mappingRows).toHaveLength(1)
    })
    expect(result.current.form.getValues('entries.0.idpGroupValue')).toBe('')
  })

  it('does not patch when save is called with incomplete entries', async () => {
    const mockMutate = vi.fn()
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.form.setValue('entries.0.idpGroupValue', 'admin')
    })
    act(() => {
      result.current.onSave()
    })

    await waitFor(() => {
      expect(result.current.form.formState.isSubmitted).toBe(true)
    })

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('patches with empty group_mapping_entries when all entries are empty', async () => {
    const mockMutate = vi.fn()
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.onSave()
    })

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    const patchArgs = mockMutate.mock.calls[0]?.[0] as
      | { body?: { configuration?: { group_mapping_entries?: unknown[] } } }
      | undefined
    expect(patchArgs?.body?.configuration?.group_mapping_entries).toEqual([])
  })

  it('patches provider and navigates on successful save', async () => {
    const mockMutate = vi.fn((_params: unknown, callbacks?: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.()
    })
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: {
            ...mockProvider.configuration,
            group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
          },
          defaultExpression: 'groups[*]',
          groupMappingConfig: {
            group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: MOCK_GROUP_ID }],
          },
          idpType: 'custom',
        }),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.form.getValues('entries.0.idpGroupValue')).toBe('admin')
    })

    act(() => {
      result.current.onSave()
    })

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })
    expect(mockShowSuccess).toHaveBeenCalledWith(expect.objectContaining({ title: 'Group mapping saved' }))
    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: `/system-administration/authentication/identity-providers/${VALID_PROVIDER_ID}/group-mapping`,
    })
  })

  it('navigates to tab on cancel', () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.onCancel()
    })

    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: `/system-administration/authentication/identity-providers/${VALID_PROVIDER_ID}/group-mapping`,
    })
  })

  it('sets sign-in error alert when test sign-in fails', () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      testSignInCallbacks.onError?.()
    })

    expect(result.current.panel.signInAlert?.variant).toBe('danger')
    expect(result.current.panel.signInAlert?.message).toContain('Could not connect to the identity provider')
  })

  it('updates entries after successful group discovery', () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      testSignInCallbacks.onResult?.({ groups: ['admin'] })
    })

    expect(result.current.panel.signInAlert?.variant).toBe('success')
    expect(result.current.form.getValues('entries').some((e) => e.idpGroupValue === 'admin')).toBe(true)
    expect(result.current.panel.rawClaims).toContain('"groups"')
  })

  it('reports matched group count after discovery when groups align with Nexus names', () => {
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [
        { id: MOCK_GROUP_ID, name: 'admin', is_builtin: false, created_at: '2026-01-01', updated_at: '2026-01-01' },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      testSignInCallbacks.onResult?.({ groups: ['admin'] })
    })

    expect(result.current.panel.signInAlert?.message).toContain('matched to groups')
  })

  it('assigns newest group after create-group flow', async () => {
    const mockRefetch = vi.fn().mockResolvedValue({
      data: [
        { id: MOCK_GROUP_ID, name: 'admin', is_builtin: false, created_at: '2026-01-01', updated_at: '2026-01-01' },
        {
          id: MOCK_NEW_GROUP_ID,
          name: 'new-team',
          is_builtin: false,
          created_at: '2026-06-03',
          updated_at: '2026-06-03',
        },
      ],
    })
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [
        { id: MOCK_GROUP_ID, name: 'admin', is_builtin: false, created_at: '2026-01-01', updated_at: '2026-01-01' },
      ],
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.form.setValue('entries.0.idpGroupValue', 'new-team')
      result.current.panel.onCreateGroup(0)
    })

    await act(async () => {
      await result.current.panel.onGroupCreated()
    })

    expect(result.current.form.getValues('entries.0.nexusGroupId')).toBe(MOCK_NEW_GROUP_ID)
    expect(result.current.panel.createGroupForIndex).toBeNull()
  })

  it('dismisses sign-in alert and appends blank mapping rows', () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      testSignInCallbacks.onResult?.({ groups: ['admin'] })
    })
    expect(result.current.panel.signInAlert).not.toBeNull()

    const entryCountBeforeAdd = result.current.form.getValues('entries').length

    act(() => {
      result.current.panel.onDismissSignInAlert()
      result.current.panel.onAdd()
    })

    expect(result.current.panel.signInAlert).toBeNull()
    expect(result.current.form.getValues('entries')).toHaveLength(entryCountBeforeAdd + 1)
    expect(result.current.form.getValues(`entries.${entryCountBeforeAdd}`)).toEqual({
      idpGroupValue: '',
      nexusGroupId: '',
    })
  })

  it('shows warning when discovery finds no groups', () => {
    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      testSignInCallbacks.onResult?.({ roles: ['admin'] })
    })

    expect(result.current.panel.signInAlert?.variant).toBe('warning')
    expect(result.current.panel.signInAlert?.message).toContain('No groups found')
  })

  it('closes create-group modal without assigning a group when refetch returns no groups', async () => {
    const mockRefetch = vi.fn().mockResolvedValue({ data: [] })
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [],
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.panel.onCreateGroup(0)
    })
    expect(result.current.panel.createGroupForIndex).toBe(0)

    act(() => {
      result.current.panel.onCloseCreateGroup()
    })
    expect(result.current.panel.createGroupForIndex).toBeNull()

    await act(async () => {
      await result.current.panel.onGroupCreated()
    })

    expect(result.current.form.getValues('entries.0.nexusGroupId')).toBe('')
    expect(result.current.panel.createGroupForIndex).toBeNull()
  })

  it('filters the built-in authenticated group from nexus group options', () => {
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [
        { id: MOCK_GROUP_ID, name: 'admin', is_builtin: false, created_at: '2026-01-01', updated_at: '2026-01-01' },
        {
          id: 'builtin-auth',
          name: 'authenticated',
          is_builtin: true,
          created_at: '2026-01-01',
          updated_at: '2026-01-01',
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    expect(result.current.panel.nexusGroups.map((group) => group.name)).toEqual(['admin'])
  })

  it('invokes mutation error handler when save fails', async () => {
    const mockMutate = vi.fn((_params: unknown, callbacks?: { onError?: (error: Error) => void }) => {
      callbacks?.onError?.(new Error('Save failed'))
    })
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.onSave()
    })

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })
    expect(mockHandleError).toHaveBeenCalledWith({ title: 'Failed to save group mapping' })
  })

  it('does not assign a group id when the newest refetched group has no id', async () => {
    const mockRefetch = vi.fn().mockResolvedValue({
      data: [{ name: 'new-team', is_builtin: false, created_at: '2026-06-03', updated_at: '2026-06-03' }],
    })
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [],
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    act(() => {
      result.current.panel.onCreateGroup(0)
    })

    await act(async () => {
      await result.current.panel.onGroupCreated()
    })

    expect(result.current.form.getValues('entries.0.nexusGroupId')).toBe('')
  })

  it('clears create-group modal when group creation completes without an active row', async () => {
    vi.mocked(useAllGroups).mockReturnValue({
      groups: [],
      isLoading: false,
      error: null,
      refetch: vi.fn().mockResolvedValue({ data: [] }),
    })

    const { result } = renderHook(
      () =>
        useGroupMappingEditForm({
          providerId: VALID_PROVIDER_ID,
          config: mockProvider.configuration,
          defaultExpression: 'groups[*]',
          groupMappingConfig: null,
          idpType: 'custom',
        }),
      { wrapper }
    )

    await act(async () => {
      await result.current.panel.onGroupCreated()
    })

    expect(result.current.panel.createGroupForIndex).toBeNull()
  })
})
