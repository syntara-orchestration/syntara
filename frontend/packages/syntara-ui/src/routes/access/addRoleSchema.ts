import { z } from 'zod'

/** Inline hint shown under the role name field before validation errors */
export const ROLE_NAME_HINT = 'Lowercase alphanumeric with hyphens (e.g. my-custom-role)'

/** Shared fields for both add and edit role forms */
export const roleBaseSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or fewer')
    .regex(
      /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
      'Name must be lowercase alphanumeric with hyphens, starting and ending with a letter or number'
    ),
  description: z.string().max(1024, 'Description must be 1024 characters or fewer').optional().or(z.literal('')),
  policies: z.array(z.string()).min(1, 'At least one policy is required'),
})

export type EditRoleFormData = z.infer<typeof roleBaseSchema>

/** Add role schema includes scope and project selection */
export const addRoleSchema = roleBaseSchema
  .extend({
    scope: z.enum(['system', 'project']),
    projectId: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.scope === 'project' && !data.projectId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Project is required for project-scoped roles',
        path: ['projectId'],
      })
    }
  })

export type AddRoleFormData = z.infer<typeof addRoleSchema>
