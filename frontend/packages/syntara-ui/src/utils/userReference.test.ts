import { describe, expect, it } from 'vitest'

import { isUserReference, toLinkedUserId, toUserReferenceId, toUserReferenceName } from './userReference'

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

describe('toUserReferenceName', () => {
  it('returns the name from a UserReference', () => {
    expect(toUserReferenceName({ id: 'u-1', name: 'alice' })).toBe('alice')
  })

  it('returns a plain string id as-is', () => {
    expect(toUserReferenceName('jane')).toBe('jane')
  })

  it.each([
    ['an empty name', { id: 'u-1', name: '' }],
    ['an empty string', ''],
    ['null', null],
    ['undefined', undefined],
    ['a non-reference value', 42],
  ])('returns undefined for %s', (_label, value) => {
    expect(toUserReferenceName(value)).toBeUndefined()
  })
})

describe('toUserReferenceId', () => {
  it('returns the id from a UserReference', () => {
    expect(toUserReferenceId({ id: 'u-1', name: 'alice' })).toBe('u-1')
  })

  it.each([
    ['a plain string', 'jane'],
    ['null', null],
    ['undefined', undefined],
  ])('returns undefined for %s', (_label, value) => {
    expect(toUserReferenceId(value)).toBeUndefined()
  })
})

describe('toLinkedUserId', () => {
  it('returns the id for a live user, which has a detail page', () => {
    expect(toLinkedUserId({ id: 'u-1', name: 'alice', type: 'user' })).toBe('u-1')
  })

  it.each([
    ['a service account', { id: 'sa-1', name: 'ci-runner', type: 'service_account' }],
    ['an internal service', { id: 'svc-1', name: 'worker.ao.svc', type: 'service' }],
    ['a legacy system principal', { id: 'sys-1', name: 'sys-1', type: 'system' }],
    ['a deleted user', { id: 'u-gone', name: 'Deleted user', type: 'deleted_user' }],
    ['a deleted service account', { id: 'sa-gone', name: 'Deleted service account', type: 'deleted_service_account' }],
    ['a reference without a type', { id: 'u-1', name: 'alice' }],
    ['a plain string', 'jane'],
    ['null', null],
    ['undefined', undefined],
  ])('returns undefined for %s (no user page to link to)', (_label, value) => {
    expect(toLinkedUserId(value)).toBeUndefined()
  })
})
