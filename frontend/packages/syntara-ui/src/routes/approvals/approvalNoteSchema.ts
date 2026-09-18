import { z } from 'zod'

import { approvalDecisionSchema } from '../executions/approvalDecisionSchema'

export const approvalNotesOnlySchema = approvalDecisionSchema.pick({ notes: true })

export type ApprovalNotesOnlyFormData = z.infer<typeof approvalNotesOnlySchema>

export const BULK_APPROVAL_NOTE_MAX_LENGTH = 1000

export const bulkApprovalNoteSchema = z.object({
  note: z.string().max(BULK_APPROVAL_NOTE_MAX_LENGTH),
})

export type BulkApprovalNoteFormData = z.infer<typeof bulkApprovalNoteSchema>
