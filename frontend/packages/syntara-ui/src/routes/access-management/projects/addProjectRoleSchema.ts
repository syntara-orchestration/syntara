import { z } from 'zod'

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
