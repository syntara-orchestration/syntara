import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { act, createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { credentialsClient, integrationsClient } from '../../../client'

import type { Credential } from './credentialConstants'
import { useDisableCredentialState } from './useDisableCredentialState'

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

type MockQueryReturn = Pick<UseQueryResult, 'data' | 'error' | 'isPending'>

function mockQuery(overrides: Partial<MockQueryReturn> = {}) {
  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: undefined,
    error: null,
    isPending: false,
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

describe('useDisableCredentialState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQuery()
  })

  it('has initial state with credentialToDisable null, affectedWorkflows empty, workflowsFetchError false', () => {
    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    expect(result.current.credentialToDisable).toBeNull()
    expect(result.current.affectedWorkflows).toEqual([])
    expect(result.current.workflowsFetchError).toBe(false)
  })

  it('sets credentialToDisable when openDisableDialog is called', () => {
    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })

    expect(result.current.credentialToDisable).toEqual(mockCredential)
  })

  it('returns affectedWorkflows from query data', () => {
    const mockWorkflows = [
      { id: 'wf-1', name: 'Workflow 1' },
      { id: 'wf-2', name: 'Workflow 2' },
    ]
    mockQuery({ data: { resources: mockWorkflows } })

    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })

    expect(result.current.affectedWorkflows).toEqual(mockWorkflows)
    expect(result.current.workflowsFetchError).toBe(false)
  })

  it('sets workflowsFetchError when query has error', () => {
    mockQuery({ error: new Error('Server error') })

    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })

    expect(result.current.workflowsFetchError).toBe(true)
    expect(result.current.affectedWorkflows).toEqual([])
  })

  it('resets credentialToDisable when closeDisableDialog is called', () => {
    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })
    expect(result.current.credentialToDisable).toEqual(mockCredential)

    act(() => {
      result.current.closeDisableDialog()
    })
    expect(result.current.credentialToDisable).toBeNull()
  })

  it('passes credential_id to useQuery params', () => {
    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })

    // Verify useQuery was called with the credential ID in the path params
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
    renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/credentials/{credential_id}/workflows',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })

  it('has initial state with affectedIntegrations empty and no integration errors', () => {
    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

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

    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
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

    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
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

    const { result } = renderHook(() => useDisableCredentialState(), { wrapper: createWrapper() })

    act(() => {
      result.current.openDisableDialog(mockCredential)
    })

    expect(result.current.isLoadingIntegrations).toBe(true)
  })
})
