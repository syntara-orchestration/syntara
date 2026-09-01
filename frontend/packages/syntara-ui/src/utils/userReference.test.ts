import { describe, expect, it } from 'vitest'

import { isUserReference, userReferenceId, userReferenceName } from './userReference'

describe('isUserReference', () => {
  it('accepts an object with string id and name', () => {
    expect(isUserReference({ id: 'u-1', name: 'alice' })).toBe(true)
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['a string', 'alice'],
    ['a number', 42],
    ['a partial object', { id: 'u-1' }],
    ['non-string fields', { id: 1, name: 2 }],
  ])('rejects %s', (_label, value) => {
    expect(isUserReference(value)).toBe(false)
  })
})

describe('userReferenceName', () => {
  it('returns the name from a UserReference', () => {
    expect(userReferenceName({ id: 'u-1', name: 'alice' })).toBe('alice')
  })

  it('returns a plain string id as-is', () => {
    expect(userReferenceName('jane')).toBe('jane')
  })

  it.each([
    ['an empty name', { id: 'u-1', name: '' }],
    ['an empty string', ''],
    ['null', null],
    ['undefined', undefined],
    ['a non-reference value', 42],
  ])('returns undefined for %s', (_label, value) => {
    expect(userReferenceName(value)).toBeUndefined()
  })
})

describe('userReferenceId', () => {
  it('returns the id from a UserReference', () => {
    expect(userReferenceId({ id: 'u-1', name: 'alice' })).toBe('u-1')
  })

  it.each([
    ['a plain string', 'jane'],
    ['null', null],
    ['undefined', undefined],
  ])('returns undefined for %s', (_label, value) => {
    expect(userReferenceId(value)).toBeUndefined()
  })
})
