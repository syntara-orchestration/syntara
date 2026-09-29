import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { act, createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { credentialsClient, integrationsClient } from '../../../client'

import type { Credential } from './credentialConstants'
import { useDeleteCredentialState } from './useDeleteCredentialState'

vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
  },
  integrationsClient: {
    useQuery: vi.fn(() => ({ data: { resources: [] }, error: null, isLoading: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

type MockQueryReturn = Pick<UseQueryResult, 'data' | 'error' | 'isPending' | 'isLoading'>

function mockQuery(overrides: Partial<MockQueryReturn> = {}) {
  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: undefined,
    error: null,
    isPending: false,
    isLoading: false,
    ...overrides,
  } as ReturnType<typeof credentialsClient.useQuery>)
}

const mockCredential: Credential = {
  id: 'cred-1',
  name: 'Test Credential',
  description: '',
  credential_type_id: 'type-1',
  inputs: {},
  enabled: true,
  labels: {},
  created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-1', type: 'user' },
  project_id: 'proj-1',
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useDeleteCredentialState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQuery()
  })

  it('has initial state with credentialToDelete null, affectedWorkflows empty, and no errors', () => {
    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    expect(result.current.credentialToDelete).toBeNull()
    expect(result.current.affectedWorkflows).toEqual([])
    expect(result.current.workflowsFetchError).toBe(false)
    expect(result.current.isLoadingWorkflows).toBe(false)
  })

  it('sets credentialToDelete when openDeleteDialog is called', () => {
    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.credentialToDelete).toEqual(mockCredential)
  })

  it('returns affectedWorkflows from query data', () => {
    const mockWorkflows = [
      { id: 'wf-1', name: 'Workflow 1' },
      { id: 'wf-2', name: 'Workflow 2' },
    ]
    mockQuery({ data: { resources: mockWorkflows } })

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.affectedWorkflows).toEqual(mockWorkflows)
    expect(result.current.workflowsFetchError).toBe(false)
  })

  it('sets workflowsFetchError when query has error', () => {
    mockQuery({ error: new Error('Server error') })

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.workflowsFetchError).toBe(true)
    expect(result.current.affectedWorkflows).toEqual([])
  })

  it('reports isLoadingWorkflows when query is loading and credential is selected', () => {
    mockQuery({ isPending: true, isLoading: true })

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.isLoadingWorkflows).toBe(true)
  })

  it('resets credentialToDelete when closeDeleteDialog is called', () => {
    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })
    expect(result.current.credentialToDelete).toEqual(mockCredential)

    act(() => {
      result.current.closeDeleteDialog()
    })
    expect(result.current.credentialToDelete).toBeNull()
  })

  it('passes credential_id to useQuery params', () => {
    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/credentials/{credential_id}/workflows',
      expect.objectContaining({
        params: { path: { credential_id: 'cred-1' } },
      }),
      expect.objectContaining({ enabled: true })
    )
  })

  it('disables query when no credential is selected', () => {
    renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/credentials/{credential_id}/workflows',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })

  it('has initial state with affectedIntegrations empty and no integration errors', () => {
    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    expect(result.current.affectedIntegrations).toEqual([])
    expect(result.current.integrationsFetchError).toBe(false)
    expect(result.current.isLoadingIntegrations).toBe(false)
  })

  it('returns affectedIntegrations from integration query data', () => {
    const mockIntegrations = [
      { id: 'int-1', name: 'GitHub Copilot' },
      { id: 'int-2', name: 'Jira Integration' },
    ]
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: mockIntegrations },
      error: null,
      isLoading: false,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.affectedIntegrations).toEqual(mockIntegrations)
    expect(result.current.integrationsFetchError).toBe(false)
  })

  it('sets integrationsFetchError when integration query fails', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: undefined,
      error: new Error('Server error'),
      isLoading: false,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.integrationsFetchError).toBe(true)
    expect(result.current.affectedIntegrations).toEqual([])
  })

  it('reports isLoadingIntegrations when integration query is loading', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useDeleteCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDeleteDialog(mockCredential)
    })

    expect(result.current.isLoadingIntegrations).toBe(true)
  })
})
