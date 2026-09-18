import { z } from 'zod'

import { approvalDecisionSchema, APPROVAL_NOTES_MAX_LENGTH } from '../executions/approvalDecisionSchema'

export const approvalNotesOnlySchema = approvalDecisionSchema.pick({ notes: true })

export type ApprovalNotesOnlyFormData = z.infer<typeof approvalNotesOnlySchema>

/** Same limit as single approval decisions (approvals API OpenAPI `maxLength: 2000`). */
export const bulkApprovalNoteSchema = z.object({
  note: z.string().max(APPROVAL_NOTES_MAX_LENGTH),
})

export type BulkApprovalNoteFormData = z.infer<typeof bulkApprovalNoteSchema>
