import { z } from 'zod'

/** Inline hint shown under the role name field before validation errors */
export const PROJECT_ROLE_NAME_HINT = 'Lowercase alphanumeric with hyphens (e.g. my-custom-role)'

export const addProjectRoleSchema = z.object({
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

export type AddProjectRoleFormData = z.infer<typeof addProjectRoleSchema>
