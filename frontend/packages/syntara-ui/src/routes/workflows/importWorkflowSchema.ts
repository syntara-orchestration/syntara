import { z } from 'zod'

export const importWorkflowSchema = z.object({
  name: z.string().min(1, 'Workflow name is required').max(255, 'Name must be 255 characters or fewer'),
  file: z
    .instanceof(File, { message: 'Workflow file is required' })
    .optional()
    .refine((value) => value instanceof File, 'Workflow file is required'),
})

export type ImportWorkflowFormData = z.infer<typeof importWorkflowSchema>
