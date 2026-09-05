import { describe, expect, it } from 'vitest'

import { extractParameters, normalizeTemplate, stableStringify } from './normalize-route'

describe('normalizeTemplate', () => {
  it('leaves TanStack templates unchanged', () => {
    expect(normalizeTemplate('/users/$userId')).toBe('/users/$userId')
  })

  it('converts AppRoute :param syntax to $param', () => {
    expect(normalizeTemplate('/users/:userId/:tab')).toBe('/users/$userId/$tab')
  })
})

describe('extractParameters', () => {
  it('returns ordered parameter names', () => {
    expect(extractParameters('/users/$userId/groups/$groupId')).toStrictEqual(['userId', 'groupId'])
  })

  it('returns an empty list for static routes', () => {
    expect(extractParameters('/workflows')).toStrictEqual([])
  })
})

describe('stableStringify', () => {
  it('sorts object keys for deterministic output', () => {
    expect(stableStringify({ b: 1, a: 2 })).toBe('{\n  "a": 2,\n  "b": 1\n}\n')
  })
})
