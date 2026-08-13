import { useMemo } from 'react'

import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'

export const PRINCIPAL_ID_FIELD: Record<RolePrincipalType, 'userId' | 'groupId' | 'serviceAccountId'> = {
  [RolePrincipalType.USER]: 'userId',
  [RolePrincipalType.GROUP]: 'groupId',
  [RolePrincipalType.SERVICE_ACCOUNT]: 'serviceAccountId',
}

export function useAlreadyAssignedRoles(
  principalType: RolePrincipalType,
  principalId: string,
  isProjectScoped: boolean,
  projectId: string
) {
  const userAssignmentsQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}/role_assignments',
    { params: { path: { user_id: principalId || '' } } },
    { enabled: principalType === RolePrincipalType.USER && !!principalId }
  )
  const groupAssignmentsQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}/role_assignments',
    { params: { path: { group_id: principalId || '' } } },
    { enabled: principalType === RolePrincipalType.GROUP && !!principalId }
  )
  const saAssignmentsQuery = accessClient.useQuery(
    'get',
    '/role_assignments',
    { params: { query: { principal_id: principalId || '' } } },
    { enabled: principalType === RolePrincipalType.SERVICE_ACCOUNT && !!principalId }
  )

  const activeData = {
    [RolePrincipalType.USER]: userAssignmentsQuery.data,
    [RolePrincipalType.GROUP]: groupAssignmentsQuery.data,
    [RolePrincipalType.SERVICE_ACCOUNT]: saAssignmentsQuery.data,
  }[principalType]

  return useMemo(() => {
    const assignments = activeData?.resources ?? []
    const assigned = new Set<string>()
    for (const a of assignments) {
      const aIsProject = !!a.project_id
      if (isProjectScoped && aIsProject && a.project_id === projectId) {
        assigned.add(a.role_name)
      } else if (!isProjectScoped && !aIsProject) {
        assigned.add(a.role_name)
      }
    }
    return assigned
  }, [activeData, isProjectScoped, projectId])
}
