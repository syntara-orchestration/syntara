import { describe, expect, it } from 'vitest'

import { getNotesLabel, hasExpandableNotes } from './approvalNotes'

describe('hasExpandableNotes', () => {
  it('returns true when decision_notes has content', () => {
    expect(hasExpandableNotes({ decision_notes: 'Looks good, approved.' })).toBe(true)
  })

  it('returns false when decision_notes is null', () => {
    expect(hasExpandableNotes({ decision_notes: null })).toBe(false)
  })

  it('returns false when decision_notes is undefined', () => {
    expect(hasExpandableNotes({ decision_notes: undefined })).toBe(false)
  })

  it('returns false when decision_notes is an empty string', () => {
    expect(hasExpandableNotes({ decision_notes: '' })).toBe(false)
  })

  it('returns false when decision_notes is only whitespace', () => {
    expect(hasExpandableNotes({ decision_notes: '   ' })).toBe(false)
  })
})

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
