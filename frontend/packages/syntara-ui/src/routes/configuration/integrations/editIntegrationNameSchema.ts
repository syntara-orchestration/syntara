import { z } from 'zod'

export const editIntegrationNameSchema = z.object({
  name: z.string().trim().min(1, 'Server name / ID is required'),
})

export type EditIntegrationNameFormData = z.infer<typeof editIntegrationNameSchema>
