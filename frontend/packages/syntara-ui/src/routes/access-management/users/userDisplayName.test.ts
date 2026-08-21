import { describe, expect, it } from 'vitest'

import { userDisplayName } from './userDisplayName'

describe('userDisplayName', () => {
  it('joins first and last name', () => {
    expect(userDisplayName({ first_name: 'John', last_name: 'Doe' })).toBe('John Doe')
  })

  it('returns only first name when last_name is null', () => {
    expect(userDisplayName({ first_name: 'Alice', last_name: null })).toBe('Alice')
  })

  it('returns only first name when last_name is undefined', () => {
    expect(userDisplayName({ first_name: 'Alice' })).toBe('Alice')
  })

  it('returns only first name when last_name is empty string', () => {
    expect(userDisplayName({ first_name: 'Alice', last_name: '' })).toBe('Alice')
  })

  it('returns empty string when first_name is empty and last_name is null', () => {
    expect(userDisplayName({ first_name: '', last_name: null })).toBe('')
  })

  it('handles last_name only when first_name is empty', () => {
    expect(userDisplayName({ first_name: '', last_name: 'Doe' })).toBe('Doe')
  })

  it('returns empty string when first_name is null and last_name is null', () => {
    expect(userDisplayName({ first_name: null, last_name: null })).toBe('')
  })
})
