import { z } from 'zod'

import { RolePrincipalType } from '../RoleAssignmentTypes'

const principalTypeValues = Object.values(RolePrincipalType) as [RolePrincipalType, ...RolePrincipalType[]]

export const assignProjectRoleSchema = z
  .object({
    principalType: z.enum(principalTypeValues),
    userId: z.string(),
    groupId: z.string(),
    serviceAccountId: z.string(),
    roleName: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.principalType === RolePrincipalType.USER && !data.userId) {
      ctx.addIssue({ code: 'custom', message: 'User is required', path: ['userId'] })
    }
    if (data.principalType === RolePrincipalType.GROUP && !data.groupId) {
      ctx.addIssue({ code: 'custom', message: 'Group is required', path: ['groupId'] })
    }
    if (data.principalType === RolePrincipalType.SERVICE_ACCOUNT && !data.serviceAccountId) {
      ctx.addIssue({ code: 'custom', message: 'Service account is required', path: ['serviceAccountId'] })
    }
    if (!data.roleName) {
      ctx.addIssue({ code: 'custom', message: 'Role is required', path: ['roleName'] })
    }
  })

export type AssignProjectRoleFormData = z.infer<typeof assignProjectRoleSchema>

export const assignProjectRoleDefaultValues: AssignProjectRoleFormData = {
  principalType: RolePrincipalType.USER,
  userId: '',
  groupId: '',
  serviceAccountId: '',
  roleName: '',
}
