import { z } from 'zod'

const namePattern = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/

/** Inline hint shown under the service account name field before validation errors */
export const SERVICE_ACCOUNT_NAME_HINT =
  'Lowercase letters, numbers, and hyphens. Must start and end with a letter or number.'

export const createServiceAccountSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or fewer')
    .regex(
      namePattern,
      'Use lowercase letters, numbers, and hyphens only. Must start and end with a letter or number.'
    ),
  description: z.string().max(2000, 'Description must be 2000 characters or fewer').optional().nullable(),
  project_id: z.string().uuid('Select a project'),
})

export type CreateServiceAccountFormData = z.infer<typeof createServiceAccountSchema>

export const editServiceAccountSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or fewer')
    .regex(
      namePattern,
      'Use lowercase letters, numbers, and hyphens only. Must start and end with a letter or number.'
    ),
  description: z.string().max(2000, 'Description must be 2000 characters or fewer').optional().nullable(),
})

export type EditServiceAccountFormData = z.infer<typeof editServiceAccountSchema>
