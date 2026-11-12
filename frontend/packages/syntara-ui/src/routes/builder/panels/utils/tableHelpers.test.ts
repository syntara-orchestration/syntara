import { describe, expect, it } from 'vitest'

import { buildRowKey, toSafeString } from './tableHelpers'

describe('toSafeString', () => {
  it('returns empty string for null', () => {
    expect(toSafeString(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(toSafeString(undefined)).toBe('')
  })

  it('returns "[Array]" for arrays', () => {
    expect(toSafeString([1, 2, 3])).toBe('[Array]')
  })

  it('returns JSON string for objects', () => {
    expect(toSafeString({ a: 1 })).toBe('{"a":1}')
  })

  it('returns string values as-is', () => {
    expect(toSafeString('hello')).toBe('hello')
  })

  it('converts numbers to string', () => {
    expect(toSafeString(42)).toBe('42')
  })

  it('converts booleans to string', () => {
    expect(toSafeString(true)).toBe('true')
    expect(toSafeString(false)).toBe('false')
  })

  it('converts bigint to string', () => {
    expect(toSafeString(BigInt(999))).toBe('999')
  })
})

describe('buildRowKey', () => {
  it('joins column values with pipe separator', () => {
    const row = { name: 'Alice', age: 30 }
    expect(buildRowKey(row, ['name', 'age'])).toBe('Alice|30')
  })

  it('handles missing columns gracefully', () => {
    const row = { name: 'Bob' }
    expect(buildRowKey(row, ['name', 'missing'])).toBe('Bob|')
  })

  it('returns empty string for empty columns', () => {
    expect(buildRowKey({}, [])).toBe('')
  })

  it('produces a stable key from the selected values', () => {
    const row = { name: 'Alice', age: 30 }
    expect(buildRowKey(row, ['name', 'age'])).toBe('Alice|30')
  })

  it('includes pipe separator characters present in values', () => {
    const row = { name: 'a|b', value: 'c' }
    expect(buildRowKey(row, ['name', 'value'])).toBe('a|b|c')
  })
})
