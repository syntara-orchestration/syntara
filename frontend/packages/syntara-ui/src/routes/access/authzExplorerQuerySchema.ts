import { z } from 'zod'

export const authzExplorerQuerySchema = z.object({
  resourceType: z.string().min(1, 'Resource type is required'),
  action: z.string().min(1, 'Action is required'),
  resourceId: z.string().optional(),
  project: z.string().optional(),
})

export type AuthzExplorerQueryFormData = z.infer<typeof authzExplorerQuerySchema>
