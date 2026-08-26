import type { FilterConfig } from '../../types/filters'
import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import type { PermissionRow, RoleAssignmentRead } from './types'

export function transformAssignmentFilters(filters: FilterConfig[]): FilterConfig[] {
  return filters.map((f) => {
    if (f.key === 'name') return { ...f, key: 'principal_name' }
    if (f.key === 'type') return { ...f, key: 'principal_type' }
    if (f.key === 'project') return { ...f, key: 'project_id' }
    return f
  })
}

export function derivePrincipalType(a: RoleAssignmentRead): RolePrincipalType {
  if (a.principal_type === 'service_account') return RolePrincipalType.SERVICE_ACCOUNT
  if (a.principal_type === 'group' || a.group_id) return RolePrincipalType.GROUP
  return RolePrincipalType.USER
}

export function buildPermissionRow(a: RoleAssignmentRead): PermissionRow {
  const isProject = !!a.project_id
  return {
    id: a.id,
    principalType: derivePrincipalType(a),
    principalId: a.principal_id ?? a.group_id ?? '',
    principalName: a.principal_name,
    assignmentType: 'role',
    assignmentName: a.role_name,
    roleDescription: a.role_description ?? null,
    rolePolicies: a.role_policies ?? [],
    scopeType: isProject ? 'project' : 'system',
    scopeName: a.project_id != null ? (a.project_name ?? a.project_id) : 'System',
    projectId: a.project_id ?? undefined,
    sourceEndpoint: isProject ? 'project-role-assignments' : 'role-assignments',
  }
}

export function buildSortParam(
  sortFields: Record<number, string>,
  activeSortIndex: number,
  defaultSortField: string,
  sortDirection: 'asc' | 'desc'
): string {
  const field = sortFields[activeSortIndex] ?? defaultSortField
  return sortDirection === 'desc' ? `-${field}` : field
}
