import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { PRINCIPAL_ID_FIELD, useAlreadyAssignedRoles } from './useAlreadyAssignedRoles'

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
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

const emptyQueryResult = {
  data: undefined,
  isPending: false,
  isError: false,
  error: null,
  isFetching: false,
  refetch: vi.fn(),
}

const mockAssignments = [
  { id: '1', role_name: 'admin', project_id: null },
  { id: '2', role_name: 'editor', project_id: 'proj-1' },
  { id: '3', role_name: 'viewer', project_id: 'proj-2' },
]

function setupQueryMock(assignments: typeof mockAssignments = []) {
  vi.mocked(accessClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/users/{user_id}/role_assignments') {
      return { ...emptyQueryResult, data: { resources: assignments } } as never
    }
    return emptyQueryResult as never
  })
}

describe('useAlreadyAssignedRoles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accessClient.useQuery).mockReturnValue(emptyQueryResult as never)
  })

  it('returns empty set when no principal is selected', () => {
    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, '', false, ''), {
      wrapper: createWrapper(),
    })

    expect(result.current.size).toBe(0)
  })

  it('returns system-scoped roles for system scope', async () => {
    setupQueryMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', false, ''), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.has('admin')).toBe(true)
    })
    expect(result.current.has('editor')).toBe(false)
    expect(result.current.has('viewer')).toBe(false)
  })

  it('returns project-scoped roles matching selected project', async () => {
    setupQueryMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', true, 'proj-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.has('editor')).toBe(true)
    })
    expect(result.current.has('admin')).toBe(false)
    expect(result.current.has('viewer')).toBe(false)
  })

  it('does not include roles from other projects', async () => {
    setupQueryMock(mockAssignments)

    const { result } = renderHook(() => useAlreadyAssignedRoles(RolePrincipalType.USER, 'user-1', true, 'proj-999'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.size).toBe(0)
    })
  })
})

describe('PRINCIPAL_ID_FIELD', () => {
  it('maps principal types to form field names', () => {
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.USER]).toBe('userId')
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.GROUP]).toBe('groupId')
    expect(PRINCIPAL_ID_FIELD[RolePrincipalType.SERVICE_ACCOUNT]).toBe('serviceAccountId')
  })
})
