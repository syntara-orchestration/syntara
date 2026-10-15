import { z } from 'zod'

export const editAssignmentSchema = z.object({
  roleName: z.string().min(1, 'Role is required'),
})

export type EditAssignmentFormData = z.infer<typeof editAssignmentSchema>
