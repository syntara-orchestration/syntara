import { describe, expect, it } from 'vitest'

import { getNotesLabel } from './approvalNotes'

describe('getNotesLabel', () => {
  it('returns "Approval notes" for approved status', () => {
    expect(getNotesLabel('approved')).toBe('Approval notes')
  })

  it('returns "Rejection notes" for rejected status', () => {
    expect(getNotesLabel('rejected')).toBe('Rejection notes')
  })

  it('returns "Notes" for other statuses', () => {
    expect(getNotesLabel('expired')).toBe('Notes')
  })

  it('returns "Notes" when status is null or undefined', () => {
    expect(getNotesLabel(null)).toBe('Notes')
    expect(getNotesLabel(undefined)).toBe('Notes')
  })
})
