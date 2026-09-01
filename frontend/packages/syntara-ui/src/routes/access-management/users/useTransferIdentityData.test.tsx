import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { usersClient } from '../../../client'

import { useIdentitiesData, useUsersPagination } from './useTransferIdentityData'

vi.mock('../../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

vi.mock('./TransferIdentityWizard.module.css', () => ({ default: {} }))

const mockUsers = {
  resources: [
    { id: 'user-1', username: 'alice', email: 'alice@example.com', first_name: 'Alice', last_name: 'Smith' },
    { id: 'user-2', username: 'bob', email: 'bob@example.com', first_name: 'Bob', last_name: 'Jones' },
    { id: 'target-user', username: 'targetuser', email: 'target@example.com', first_name: 'Target', last_name: 'User' },
  ],
  next: 'cursor-abc',
  total: 3,
}

const mockIdentities = [
  {
    id: 'id-1',
    user_id: 'user-2',
    identity_provider_id: 'p-1',
    issuer: 'https://idp.example.com',
    subject: 'sub-1',
    created_at: '2026-01-01T00:00:00Z',
    provider_name: 'Azure',
  },
  {
    id: 'id-2',
    user_id: 'user-2',
    identity_provider_id: 'p-2',
    issuer: 'https://idp2.example.com',
    subject: 'sub-2',
    created_at: '2026-02-01T00:00:00Z',
    provider_name: 'Okta',
  },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe('useUsersPagination', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.mocked(usersClient.useQuery).mockImplementation((_method, path) => {
      if (path === '/users') {
        return { data: mockUsers, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
      }
      return { data: { resources: [] }, isPending: false, isError: false, error: null, refetch: vi.fn() } as never
    })
  })

  it('returns sorted users excluding the target user', () => {
    const { result } = renderHook(() => useUsersPagination('target-user'), { wrapper })

    const usernames = result.current.sortedUsers.map((u) => u.username)
    expect(usernames).toContain('alice')
    expect(usernames).toContain('bob')
    expect(usernames).not.toContain('targetuser')
  })

  it('provides pagination footer props', () => {
    const { result } = renderHook(() => useUsersPagination('target-user'), { wrapper })

    expect(result.current.footerProps.page).toBe(1)
    expect(result.current.footerProps.perPage).toBe(20)
    expect(result.current.footerProps.hasNext).toBe(true)
  })

  it('provides filter and sort state', () => {
    const { result } = renderHook(() => useUsersPagination('target-user'), { wrapper })

    expect(result.current.usersFilter.filters).toEqual([])
    expect(result.current.usersSort.activeSortIndex).toBe(0)
  })

  it('provides a resetPage function', () => {
    const { result } = renderHook(() => useUsersPagination('target-user'), { wrapper })

    expect(typeof result.current.resetPage).toBe('function')
  })
})

describe('useIdentitiesData', () => {
  beforeEach(() => {
    queryClient.clear()
  })

  it('returns empty identities when no user is selected', () => {
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [], next: null, total: 0 },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useIdentitiesData(undefined), { wrapper })

    expect(result.current.sortedIdentities).toEqual([])
  })

  it('returns sorted identities when a user is selected', () => {
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: mockIdentities, next: null, total: 2 },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useIdentitiesData('user-2'), { wrapper })

    expect(result.current.sortedIdentities).toHaveLength(2)
    expect(result.current.sortedIdentities[0].provider_name).toBe('Azure')
    expect(result.current.sortedIdentities[1].provider_name).toBe('Okta')
  })

  it('provides filter and sort state', () => {
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [], next: null, total: 0 },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useIdentitiesData('user-2'), { wrapper })

    expect(result.current.identitiesFilter.filters).toEqual([])
    expect(result.current.identitiesSort.activeSortIndex).toBe(0)
  })
})
