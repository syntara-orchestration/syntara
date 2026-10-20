import type { Approval } from '@syntara/contracts'

/** Whether an approval has non-empty decision notes worth showing in an expandable row. */
export function hasExpandableNotes(approval: Pick<Approval, 'decision_notes'>): boolean {
  return Boolean(approval.decision_notes?.trim())
}

/** Status-appropriate label for decision notes, matching the approval detail panel. */
export function getNotesLabel(status?: string | null): string {
  if (status === 'approved') return 'Approval notes'
  if (status === 'rejected') return 'Rejection notes'
  return 'Notes'
}
