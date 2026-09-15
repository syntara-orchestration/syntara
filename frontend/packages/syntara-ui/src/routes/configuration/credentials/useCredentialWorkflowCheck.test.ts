import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { credentialsClient } from '../../../client'

import type { Credential } from './credentialConstants'
import { useCredentialWorkflowCheck } from './useCredentialWorkflowCheck'

vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

type MockQueryReturn = Pick<UseQueryResult, 'data' | 'error' | 'isLoading'>

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

function mockQuery(overrides: Partial<MockQueryReturn> = {}) {
  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: undefined,
    error: null,
    isLoading: false,
    ...overrides,
  } as ReturnType<typeof credentialsClient.useQuery>)
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useCredentialWorkflowCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQuery()
  })

  it('returns empty workflows when credential is null', () => {
    const { result } = renderHook(() => useCredentialWorkflowCheck(null), { wrapper: createWrapper() })

    expect(result.current.affectedWorkflows).toEqual([])
    expect(result.current.workflowsFetchError).toBe(false)
    expect(result.current.isLoadingWorkflows).toBe(false)
  })

  it('disables query when credential is null', () => {
    renderHook(() => useCredentialWorkflowCheck(null), { wrapper: createWrapper() })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/credentials/{credential_id}/workflows',
      expect.anything(),
      expect.objectContaining({ enabled: false })
    )
  })

  it('enables query when credential is provided', () => {
    renderHook(() => useCredentialWorkflowCheck(mockCredential), { wrapper: createWrapper() })

    expect(credentialsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/credentials/{credential_id}/workflows',
      expect.objectContaining({
        params: { path: { credential_id: 'cred-1' } },
      }),
      expect.objectContaining({ enabled: true })
    )
  })

  it('returns workflows from query data', () => {
    const mockWorkflows = [
      { id: 'wf-1', name: 'Workflow 1' },
      { id: 'wf-2', name: 'Workflow 2' },
    ]
    mockQuery({ data: { resources: mockWorkflows } })

    const { result } = renderHook(() => useCredentialWorkflowCheck(mockCredential), { wrapper: createWrapper() })

    expect(result.current.affectedWorkflows).toEqual(mockWorkflows)
  })

  it('sets workflowsFetchError when query has error', () => {
    mockQuery({ error: new Error('Server error') })

    const { result } = renderHook(() => useCredentialWorkflowCheck(mockCredential), { wrapper: createWrapper() })

    expect(result.current.workflowsFetchError).toBe(true)
    expect(result.current.affectedWorkflows).toEqual([])
  })

  it('reports isLoadingWorkflows when query is loading and credential is present', () => {
    mockQuery({ isLoading: true })

    const { result } = renderHook(() => useCredentialWorkflowCheck(mockCredential), { wrapper: createWrapper() })

    expect(result.current.isLoadingWorkflows).toBe(true)
  })

  it('does not report isLoadingWorkflows when credential is null even if query shows loading', () => {
    mockQuery({ isLoading: true })

    const { result } = renderHook(() => useCredentialWorkflowCheck(null), { wrapper: createWrapper() })

    expect(result.current.isLoadingWorkflows).toBe(false)
  })

  it('defaults affectedWorkflows to empty array when data is undefined', () => {
    mockQuery({ data: undefined })

    const { result } = renderHook(() => useCredentialWorkflowCheck(mockCredential), { wrapper: createWrapper() })

    expect(result.current.affectedWorkflows).toEqual([])
  })
})
