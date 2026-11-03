import { z } from 'zod'

export const APPROVAL_NOTES_MAX_LENGTH = 2000

export const approvalDecisionSchema = z.object({
  status: z.enum(['approved', 'rejected']),
  notes: z.string().max(APPROVAL_NOTES_MAX_LENGTH),
})

export type ApprovalDecisionFormData = z.infer<typeof approvalDecisionSchema>
