import { z } from 'zod'

export const editVersionSchema = z.object({
  name: z.string().max(255).optional().or(z.literal('')),
  change_description: z.string().max(1024).optional().or(z.literal('')),
})

export type EditVersionFormData = z.infer<typeof editVersionSchema>
