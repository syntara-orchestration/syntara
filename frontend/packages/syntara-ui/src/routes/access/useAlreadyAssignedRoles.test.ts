import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessFetchClient } from './accessClient'
import { PRINCIPAL_ID_FIELD, useAlreadyAssignedRoles } from './useAlreadyAssignedRoles'

vi.mock('./accessClient', () => ({
  accessFetchClient: {
    GET: vi.fn(),
  },
  accessClient: {},
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const mockAssignments = [
  { id: '1', role_name: 'admin', project_id: null },
  { id: '2', role_name: 'editor', project_id: 'proj-1' },
  { id: '3', role_name: 'viewer', project_id: 'proj-2' },
]

function setupFetchMock(assignments: typeof mockAssignments = []) {
  vi.mocked(accessFetchClient.GET).mockResolvedValue({
    data: { resources: assignments, next: null },
    error: undefined,
  } as never)
}

describe('useAlreadyAssignedRoles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupFetchMock()
  })

  it('returns empty set when no principal is selected', () => {
    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, '', false, ''), {
      wrapper: createWrapper(),
    })

    expect(result.current.assigned.size).toBe(0)
    expect(result.current.isLoading).toBe(false)
  })

  it('returns system-scoped roles for USER principal', async () => {
    setupFetchMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', false, ''), {
      wrapper: createWrapper(),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.assigned.has('admin')).toBe(true)
    })
    expect(result.current.assigned.has('editor')).toBe(false)
    expect(result.current.assigned.has('viewer')).toBe(false)
    expect(result.current.isLoading).toBe(false)

    const userCall = vi
      .mocked(accessFetchClient.GET)
      .mock.calls.find((c) => c[0] === '/users/{user_id}/role_assignments')
    expect(userCall).toBeDefined()
    expect(userCall?.[1]).toMatchObject({ params: { path: { user_id: 'user-1' } } })
  })

  it('returns project-scoped roles matching selected project', async () => {
    setupFetchMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', true, 'proj-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.assigned.has('editor')).toBe(true)
    })
    expect(result.current.assigned.has('admin')).toBe(false)
    expect(result.current.assigned.has('viewer')).toBe(false)
  })

  it('does not include roles from other projects', async () => {
    setupFetchMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', true, 'proj-999'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.assigned.size).toBe(0)
  })

  it('returns roles for GROUP principal type', async () => {
    setupFetchMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.GROUP, 'group-1', false, ''), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.assigned.has('admin')).toBe(true)
    })

    const groupCall = vi
      .mocked(accessFetchClient.GET)
      .mock.calls.find((c) => c[0] === '/groups/{group_id}/role_assignments')
    expect(groupCall).toBeDefined()
    expect(groupCall?.[1]).toMatchObject({ params: { path: { group_id: 'group-1' } } })
  })

  it('returns roles for SERVICE_ACCOUNT principal type', async () => {
    setupFetchMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.SERVICE_ACCOUNT, 'sa-1', false, ''), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.assigned.has('admin')).toBe(true)
    })

    const saCall = vi.mocked(accessFetchClient.GET).mock.calls.find((c) => c[0] === '/role_assignments')
    expect(saCall).toBeDefined()
    expect(saCall?.[1]).toMatchObject({ params: { query: { principal_id: 'sa-1' } } })
  })
})

describe('PRINCIPAL_ID_FIELD', () => {
  it('maps principal types to form field names', () => {
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.USER]).toBe('userId')
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.GROUP]).toBe('groupId')
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.SERVICE_ACCOUNT]).toBe('serviceAccountId')
  })
})
