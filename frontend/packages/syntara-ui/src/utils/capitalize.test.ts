import { describe, expect, it } from 'vitest'

import { capitalize } from './capitalize'

describe('capitalize', () => {
  it('uppercases the first character', () => {
    expect(capitalize('pending')).toBe('Pending')
  })

  it('leaves the rest of the string unchanged', () => {
    expect(capitalize('completed_with_errors')).toBe('Completed_with_errors')
  })

  it('returns an empty string unchanged', () => {
    expect(capitalize('')).toBe('')
  })

  it('handles a single character', () => {
    expect(capitalize('a')).toBe('A')
  })
})
