import { useMemo } from 'react'

import { getErrorCode, getErrorStatus } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { accessClient } from '../access/accessClient'

import { RolePrincipalType } from './RoleAssignmentTypes'

type PolicyInfo = {
  name: string
}

export type RoleAssignmentRow = {
  id: string
  roleName: string
  roleDescription: string | null
  policies: PolicyInfo[]
  scope: string
  scopeType: 'system' | 'project'
  createdAt: string | null
  projectId?: string
}

export function useRoleAssignmentData(principalType: RolePrincipalType, principalId: string) {
  const userAssignmentsQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}/role_assignments',
    { params: { path: { user_id: principalId } } },
    { enabled: principalType === RolePrincipalType.USER, retry: false }
  )

  const groupAssignmentsQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}/role_assignments',
    { params: { path: { group_id: principalId } } },
    { enabled: principalType === RolePrincipalType.GROUP, retry: false }
  )

  const saAssignmentsQuery = accessClient.useQuery(
    'get',
    '/role_assignments',
    { params: { query: { principal_id: principalId } } },
    { enabled: principalType === RolePrincipalType.SERVICE_ACCOUNT, retry: false }
  )

  const queryMap = {
    user: userAssignmentsQuery,
    group: groupAssignmentsQuery,
    service_account: saAssignmentsQuery,
  }
  const activeQuery = queryMap[principalType]

  const queryForbidden = useMemo(() => {
    if (!activeQuery.isError) return false
    const status = getErrorStatus(activeQuery.error)
    if (status === 403) return true
    return getErrorCode(activeQuery.error) === 'AUTHORIZATION_DENIED'
  }, [activeQuery.isError, activeQuery.error])

  const assignmentRows = useMemo((): RoleAssignmentRow[] => {
    if (queryForbidden) return []

    const assignments = activeQuery.data?.resources ?? []

    return assignments.map((a) => {
      const policyNames = a.role_policies ?? []
      const isProject = !!a.project_id
      return {
        id: a.id,
        roleName: a.role_name,
        roleDescription: a.role_description ?? null,
        policies: policyNames.map((name) => ({ name })),
        scope: a.project_id != null ? (a.project_name ?? a.project_id) : 'System',
        scopeType: isProject ? ('project' as const) : ('system' as const),
        createdAt: a.created_at ?? null,
        projectId: a.project_id ?? undefined,
      }
    })
  }, [queryForbidden, activeQuery.data])

  const { mutate: deleteRoleAssignment } = accessClient.useMutation('delete', '/role_assignments/{assignment_id}')
  const { mutate: deleteProjectRoleAssignment } = accessClient.useMutation(
    'delete',
    '/projects/{project_id}/role_assignments/{assignment_id}'
  )

  const deleteAssignment = (
    row: RoleAssignmentRow,
    callbacks: { onSuccess: () => void; onError: (err: unknown) => void; onSettled: () => void }
  ) => {
    if (row.projectId) {
      deleteProjectRoleAssignment({ params: { path: { project_id: row.projectId, assignment_id: row.id } } }, callbacks)
    } else {
      deleteRoleAssignment({ params: { path: { assignment_id: row.id } } }, callbacks)
    }
  }

  const refetch = () => {
    detachPromise(activeQuery.refetch())
  }

  return {
    rows: assignmentRows,
    queryForbidden,
    activeQuery,
    isLoading: activeQuery.isPending,
    deleteAssignment,
    refetch,
  }
}
