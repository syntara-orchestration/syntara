export const RolePrincipalType = {
  USER: 'user',
  GROUP: 'group',
  SERVICE_ACCOUNT: 'service_account',
} as const

export type RolePrincipalType = (typeof RolePrincipalType)[keyof typeof RolePrincipalType]

/** API scope values for role assignments (system-wide vs project-scoped). */
export const RoleAssignmentScope = {
  SYSTEM: 'system',
  PROJECT: 'project',
} as const

export type RoleAssignmentScope = (typeof RoleAssignmentScope)[keyof typeof RoleAssignmentScope]

/** Select options for assignment scope (API values with display labels). */
export const roleAssignmentScopeOptions: { value: RoleAssignmentScope; label: string }[] = [
  { value: RoleAssignmentScope.SYSTEM, label: 'System' },
  { value: RoleAssignmentScope.PROJECT, label: 'Project' },
]

type PrincipalTypeLabelColor = 'teal' | 'orange' | 'purple'

/** Display config for principal type labels in assignment tables (UX skill §11). */
export const principalTypeDisplay: Record<RolePrincipalType, { text: string; color: PrincipalTypeLabelColor }> = {
  [RolePrincipalType.USER]: { text: 'User', color: 'teal' },
  [RolePrincipalType.GROUP]: { text: 'Group', color: 'orange' },
  [RolePrincipalType.SERVICE_ACCOUNT]: { text: 'Service account', color: 'purple' },
}

export const principalTypeLabel: Record<RolePrincipalType, string> = {
  user: 'user',
  group: 'group',
  service_account: 'service account',
}

export function buildAssignmentBody(
  principalType: RolePrincipalType,
  principalId: string,
  roleName: string
): { principal_id?: string; group_id?: string; role_name: string } {
  if (principalType === RolePrincipalType.GROUP) {
    return { group_id: principalId, role_name: roleName }
  }
  return { principal_id: principalId, role_name: roleName }
}
