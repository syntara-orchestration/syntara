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

/**
 * A pattern assignment has no project_id but is not system-wide: it denies only in
 * projects whose name matches the pattern, so it is shown with the pattern as its scope.
 */
export function formatProjectPatternScope(pattern: string): string {
  return `Projects matching ${pattern}`
}

export function buildPermissionRow(a: RoleAssignmentRead): PermissionRow {
  const isProject = !!a.project_id
  const projectPattern = a.project_pattern ?? undefined
  return {
    id: a.id,
    isBuiltin: a.is_builtin,
    principalType: derivePrincipalType(a),
    principalId: a.principal_id ?? a.group_id ?? '',
    principalName: a.principal_name,
    assignmentType: 'role',
    assignmentName: a.role_name,
    roleDescription: a.role_description ?? null,
    rolePolicies: a.role_policies ?? [],
    scopeType: isProject || projectPattern ? 'project' : 'system',
    scopeName: scopeNameFor(a, projectPattern),
    projectId: a.project_id ?? undefined,
    projectPattern,
    sourceEndpoint: isProject ? 'project-role-assignments' : 'role-assignments',
  }
}

function scopeNameFor(a: RoleAssignmentRead, projectPattern: string | undefined): string {
  if (a.project_id != null) return a.project_name ?? a.project_id
  if (projectPattern) return formatProjectPatternScope(projectPattern)
  return 'System'
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
