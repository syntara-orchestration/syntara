import { describe, expect, it } from 'vitest'

import { escapeRegExp, regExpPrefixMatch } from './escapeRegExp'

describe('escapeRegExp', () => {
  it('escapes metacharacters', () => {
    expect(escapeRegExp('a+b (test)')).toBe('a\\+b \\(test\\)')
  })

  it('returns literals unchanged when there are no specials', () => {
    expect(escapeRegExp('HTTP Bearer Token')).toBe('HTTP Bearer Token')
  })
})

describe('regExpPrefixMatch', () => {
  it('matches when extra text follows the prefix', () => {
    const pattern = regExpPrefixMatch('HTTP Bearer Token')
    expect('HTTP Bearer Token Authenticate with a bearer token.').toMatch(pattern)
    expect('SSH Key').not.toMatch(pattern)
  })
})
