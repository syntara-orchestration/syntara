import { zodResolver } from '@hookform/resolvers/zod'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { assignRoleSchema, type AssignRoleFormData } from './assignRoleSchema'
import { useSelectableProjects } from './useAllProjects'
import { useAlreadyAssignedRoles } from './useAlreadyAssignedRoles'
import { useAssignRoleFormQueries } from './useAssignRoleFormQueries'

vi.mock('./accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
}))

vi.mock('./useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

vi.mock('./useAlreadyAssignedRoles', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./useAlreadyAssignedRoles')>()
  return {
    ...actual,
    useAlreadyAssignedRoles: vi.fn(),
  }
})

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function mockQueryData<T>(resources: T[]) {
  return {
    data: { resources },
    isLoading: false,
    error: null,
  } as never
}

function renderQueriesHook(overrides?: Partial<AssignRoleFormData>) {
  return renderHook(
    () => {
      const form = useForm<AssignRoleFormData>({
        resolver: zodResolver(assignRoleSchema),
        defaultValues: {
          principalType: RolePrincipalType.USER,
          scope: 'system',
          userId: 'user-1',
          groupId: '',
          serviceAccountId: '',
          projectId: '',
          roleName: '',
          ...overrides,
        },
      })
      return useAssignRoleFormQueries(form.control)
    },
    { wrapper: createWrapper() }
  )
}

describe('useAssignRoleFormQueries', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(useSelectableProjects).mockReturnValue({
      projects: [{ id: 'proj-1', name: 'Project One' }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(useAlreadyAssignedRoles).mockReturnValue({
      assigned: new Set(['admin']),
      isLoading: false,
      isError: false,
    })

    vi.mocked(accessClient.useQuery).mockImplementation((_method, path) => {
      if (path === '/roles') {
        return mockQueryData([{ name: 'admin' }, { name: 'editor' }, { name: 'viewer' }])
      }
      if (path === '/projects/{project_id}/roles') {
        return mockQueryData([{ name: 'project-admin' }, { name: 'admin' }])
      }
      if (path === '/users/directory') {
        return mockQueryData([{ id: 'user-1', username: 'alice' }])
      }
      return mockQueryData([])
    })
  })

  it('filters already-assigned roles from system role options', async () => {
    const { result } = renderQueriesHook()

    await waitFor(() => {
      expect(result.current.roleOptions.map((o) => o.value)).toEqual(['editor', 'viewer'])
    })
  })

  it('uses project-scoped roles when scope is project', async () => {
    const { result } = renderQueriesHook({ scope: 'project', projectId: 'proj-1' })

    await waitFor(() => {
      expect(result.current.roleOptions.map((o) => o.value)).toEqual(['project-admin'])
    })
  })

  it('returns empty role options while assignments are loading', () => {
    vi.mocked(useAlreadyAssignedRoles).mockReturnValue({
      assigned: new Set(),
      isLoading: true,
      isError: false,
    })

    const { result } = renderQueriesHook()

    expect(result.current.roleOptions).toEqual([])
  })
})
