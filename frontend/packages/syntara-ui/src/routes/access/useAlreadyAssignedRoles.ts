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

export function useAlreadyAssignedRoles(
  principalType: RolePrincipalType,
  principalId: string,
  isProjectScoped: boolean,
  projectId: string
) {
  const { data: assignments } = useQuery({
    queryKey: ['role-assignments', principalType, principalId],
    queryFn: () => fetchAssignments(principalType, principalId),
    enabled: !!principalId,
  })

  return useMemo(() => {
    const items = assignments ?? []
    const assigned = new Set<string>()
    for (const a of items) {
      const aIsProject = !!a.project_id
      if (isProjectScoped && aIsProject && a.project_id === projectId) {
        assigned.add(a.role_name)
      } else if (!isProjectScoped && !aIsProject) {
        assigned.add(a.role_name)
      }
    }
    return assigned
  }, [assignments, isProjectScoped, projectId])
}
