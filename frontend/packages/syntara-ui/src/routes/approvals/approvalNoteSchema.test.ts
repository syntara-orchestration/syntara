import { APPROVAL_NOTES_MAX_LENGTH } from '../executions/approvalDecisionSchema'

import { approvalNotesOnlySchema, bulkApprovalNoteSchema } from './approvalNoteSchema'

describe('approvalNoteSchema', () => {
  describe('approvalNotesOnlySchema', () => {
    it('accepts notes at the API max length', () => {
      const result = approvalNotesOnlySchema.safeParse({ notes: 'a'.repeat(APPROVAL_NOTES_MAX_LENGTH) })

      expect(result.success).toBe(true)
    })

    it('rejects notes over the API max length', () => {
      const result = approvalNotesOnlySchema.safeParse({ notes: 'a'.repeat(APPROVAL_NOTES_MAX_LENGTH + 1) })

      expect(result.success).toBe(false)
    })
  })

  describe('bulkApprovalNoteSchema', () => {
    it('accepts bulk notes at the API max length', () => {
      const result = bulkApprovalNoteSchema.safeParse({ note: 'a'.repeat(APPROVAL_NOTES_MAX_LENGTH) })

      expect(result.success).toBe(true)
    })

    it('rejects bulk notes over the API max length', () => {
      const result = bulkApprovalNoteSchema.safeParse({ note: 'a'.repeat(APPROVAL_NOTES_MAX_LENGTH + 1) })

      expect(result.success).toBe(false)
    })
  })
})
