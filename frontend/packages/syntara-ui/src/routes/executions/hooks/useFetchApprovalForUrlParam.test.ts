import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { approvalsClient } from '../../../client'

import { useFetchApprovalForUrlParam } from './useFetchApprovalForUrlParam'

vi.mock('../../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useFetchApprovalForUrlParam', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })

  it('returns undefined when no approval param in URL', () => {
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: undefined,
    })

    const { result } = renderHook(() => useFetchApprovalForUrlParam(''), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toBeUndefined()
  })

  it('fetches approval when approval param is present', () => {
    const mockApproval = { id: 'approval-1', name: 'Test' }
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: mockApproval,
    })

    const { result } = renderHook(() => useFetchApprovalForUrlParam('approval=approval-1'), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual(mockApproval)
    expect(approvalsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/approvals/{approval_id}',
      { params: { path: { approval_id: 'approval-1' } } },
      { enabled: true }
    )
  })

  it('passes enabled=false when no approval param', () => {
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: undefined,
    })

    renderHook(() => useFetchApprovalForUrlParam('history=open'), {
      wrapper: makeWrapper(queryClient),
    })

    expect(approvalsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/approvals/{approval_id}',
      { params: { path: { approval_id: '' } } },
      { enabled: false }
    )
  })

  it('handles searchParams with question mark prefix', () => {
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: undefined,
    })

    renderHook(() => useFetchApprovalForUrlParam('?approval=test-id'), {
      wrapper: makeWrapper(queryClient),
    })

    expect(approvalsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/approvals/{approval_id}',
      { params: { path: { approval_id: 'test-id' } } },
      { enabled: true }
    )
  })
})
