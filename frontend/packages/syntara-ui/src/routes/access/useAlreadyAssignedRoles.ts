import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { fetchAllPages, MAX_PAGE_SIZE } from '../../utils/fetchAllPages'
import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessFetchClient } from './accessClient'

export const PRINCIPAL_ID_FIELD: Record<RolePrincipalType, 'userId' | 'groupId' | 'serviceAccountId'> = {
  [RolePrincipalType.USER]: 'userId',
  [RolePrincipalType.GROUP]: 'groupId',
  [RolePrincipalType.SERVICE_ACCOUNT]: 'serviceAccountId',
}

type RoleAssignment = {
  role_name: string
  project_id?: string | null
}

function fetchAssignments(principalType: RolePrincipalType, principalId: string): Promise<RoleAssignment[]> {
  switch (principalType) {
    case RolePrincipalType.USER:
      return fetchAllPages<RoleAssignment>((cursor) =>
        accessFetchClient.GET('/users/{user_id}/role_assignments', {
          params: { path: { user_id: principalId }, query: { limit: MAX_PAGE_SIZE, cursor } },
        })
      )
    case RolePrincipalType.GROUP:
      return fetchAllPages<RoleAssignment>((cursor) =>
        accessFetchClient.GET('/groups/{group_id}/role_assignments', {
          params: { path: { group_id: principalId }, query: { limit: MAX_PAGE_SIZE, cursor } },
        })
      )
    case RolePrincipalType.SERVICE_ACCOUNT:
      return fetchAllPages<RoleAssignment>((cursor) =>
        accessFetchClient.GET('/role_assignments', {
          params: { query: { principal_id: principalId, limit: MAX_PAGE_SIZE, cursor } },
        })
      )
  }
}

export function roleAssignmentsQueryKey(principalType: RolePrincipalType, principalId: string) {
  return ['role-assignments', principalType, principalId] as const
}

export function useAlreadyAssignedRoles(
  principalType: RolePrincipalType,
  principalId: string,
  isProjectScoped: boolean,
  projectId: string
) {
  const {
    data: assignments,
    isPending,
    isError,
  } = useQuery({
    queryKey: roleAssignmentsQueryKey(principalType, principalId),
    queryFn: () => fetchAssignments(principalType, principalId),
    enabled: !!principalId,
  })

  const isLoading = !!principalId && isPending

  const assigned = useMemo(() => {
    const items = assignments ?? []
    const result = new Set<string>()
    for (const a of items) {
      const aIsProject = !!a.project_id
      const matches = isProjectScoped ? aIsProject && a.project_id === projectId : !aIsProject
      if (matches) {
        result.add(a.role_name)
      }
    }
    return result
  }, [assignments, isProjectScoped, projectId])

  return { assigned, isLoading, isError }
}
