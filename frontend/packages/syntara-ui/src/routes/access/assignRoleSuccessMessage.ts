import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import type { AssignRoleFormData } from './assignRoleSchema'

type NamedOption = { value: string; label: string }

export function assignmentAddedDescription(
  data: AssignRoleFormData,
  userOptions: NamedOption[],
  groupOptions: NamedOption[],
  serviceAccountOptions: NamedOption[]
): string {
  const optionsByType = {
    [RolePrincipalType.USER]: userOptions,
    [RolePrincipalType.GROUP]: groupOptions,
    [RolePrincipalType.SERVICE_ACCOUNT]: serviceAccountOptions,
  }
  const idByType = {
    [RolePrincipalType.USER]: data.userId,
    [RolePrincipalType.GROUP]: data.groupId,
    [RolePrincipalType.SERVICE_ACCOUNT]: data.serviceAccountId,
  }
  const principalId = idByType[data.principalType]
  const principalName =
    optionsByType[data.principalType].find((option) => option.value === principalId)?.label ?? principalId
  return `Assignment for ${principalName} has been added.`
}
