/** Status-appropriate label for decision notes, matching the approval detail panel. */
export function getNotesLabel(status?: string | null): string {
  if (status === 'approved') return 'Approval notes'
  if (status === 'rejected') return 'Rejection notes'
  return 'Notes'
}
