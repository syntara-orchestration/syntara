import { z } from 'zod'

import { RoleAssignmentScope } from './RoleAssignmentTypes'

const roleAssignmentScopeValues = Object.values(RoleAssignmentScope) as [RoleAssignmentScope, ...RoleAssignmentScope[]]

/**
 * Zod schema for the assign-role modal form.
 * Scope drives conditional project validation via superRefine (RHF-friendly).
 */
export const assignRoleFormSchema = z
  .object({
    scope: z.enum(roleAssignmentScopeValues),
    projectId: z.string().optional(),
    roleIds: z.array(z.string()).min(1, 'Select at least one role'),
  })
  .superRefine((data, ctx) => {
    if (data.scope === RoleAssignmentScope.PROJECT && !data.projectId?.trim()) {
      ctx.addIssue({
        code: 'custom',
        message: 'Project is required',
        path: ['projectId'],
      })
    }
  })

export type AssignRoleFormData = z.infer<typeof assignRoleFormSchema>
