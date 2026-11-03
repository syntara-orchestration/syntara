import { z } from 'zod'

export const publishWorkflowSchema = z.object({
  name: z.string().min(1, 'Version name is required').max(255),
  description: z.string().max(1000, 'Description must be 1000 characters or fewer').optional().or(z.literal('')),
})

export type PublishWorkflowFormData = z.infer<typeof publishWorkflowSchema>
