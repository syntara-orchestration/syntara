import { z } from 'zod'

/**
 * Zod schema for the Permission check node form.
 *
 * The node kind has no configuration of its own: it always evaluates the single
 * node immediately upstream and routes to `allowed` or `denied`. Only the step
 * name is editable.
 */
export const permissionCheckFormSchema = z.object({
  name: z.string(),
})

export type PermissionCheckFormData = z.infer<typeof permissionCheckFormSchema>
