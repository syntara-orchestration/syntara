import { describe, expect, it } from 'vitest'

import { userDisplayName } from './userDisplayName'

describe('userDisplayName', () => {
  it('joins first and last name', () => {
    expect(userDisplayName({ first_name: 'John', last_name: 'Doe', username: 'jdoe' })).toBe('John Doe')
  })

  it('returns only first name when last_name is null', () => {
    expect(userDisplayName({ first_name: 'Alice', last_name: null, username: 'alice' })).toBe('Alice')
  })

  it('returns only first name when last_name is undefined', () => {
    expect(userDisplayName({ first_name: 'Alice', username: 'alice' })).toBe('Alice')
  })

  it('returns only first name when last_name is empty string', () => {
    expect(userDisplayName({ first_name: 'Alice', last_name: '', username: 'alice' })).toBe('Alice')
  })

  it('falls back to username when first_name is empty and last_name is null', () => {
    expect(userDisplayName({ first_name: '', last_name: null, username: 'jdoe' })).toBe('jdoe')
  })

  it('handles last_name only when first_name is empty', () => {
    expect(userDisplayName({ first_name: '', last_name: 'Doe', username: 'jdoe' })).toBe('Doe')
  })

  it('handles last_name only when first_name is whitespace', () => {
    expect(userDisplayName({ first_name: '   ', last_name: 'Doe', username: 'jdoe' })).toBe('Doe')
  })

  it('falls back to username when first_name and last_name are null', () => {
    expect(userDisplayName({ first_name: null, last_name: null, username: 'jdoe' })).toBe('jdoe')
  })

  it('falls back to username when names are whitespace', () => {
    expect(userDisplayName({ first_name: '   ', last_name: '  ', username: 'jdoe' })).toBe('jdoe')
  })

  it('strips whitespace around names', () => {
    expect(userDisplayName({ first_name: ' Jane ', last_name: ' Doe ', username: 'jdoe' })).toBe('Jane Doe')
  })
})
