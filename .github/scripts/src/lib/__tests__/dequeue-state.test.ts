import { describe, expect, it } from 'vitest'
import { hasNewDequeueSince } from '../dequeue-state.js'

describe('hasNewDequeueSince', () => {
  it('detects dequeues after the previous run even when the poll was delayed', () => {
    expect(hasNewDequeueSince([{ dequeuedAt: '2026-08-27T12:10:00Z' }], new Date('2026-08-27T12:00:00Z'))).toBe(true)
  })

  it('does not replay dequeues already covered by the previous run', () => {
    expect(hasNewDequeueSince([{ dequeuedAt: '2026-08-27T12:10:00Z' }], new Date('2026-08-27T12:15:00Z'))).toBe(false)
  })
})
