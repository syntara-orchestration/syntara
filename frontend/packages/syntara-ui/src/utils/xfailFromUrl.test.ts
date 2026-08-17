import { describe, expect, it } from 'vitest'

import { matchPattern, parseXfailEntries } from '../../e2e/xfailFromUrl'

describe('parseXfailEntries', () => {
  it('parses a single heading with reason', () => {
    const content = '# tests/unit/test_foo.py\nflaky on CI'
    expect(parseXfailEntries(content)).toEqual([{ pattern: 'tests/unit/test_foo.py', reason: 'flaky on CI' }])
  })

  it('parses multiple headings', () => {
    const content = ['# pattern-one', 'reason one', '', '# pattern-two', 'reason two'].join('\n')
    expect(parseXfailEntries(content)).toEqual([
      { pattern: 'pattern-one', reason: 'reason one' },
      { pattern: 'pattern-two', reason: 'reason two' },
    ])
  })

  it('uses default reason when body is empty', () => {
    const content = '# some-pattern\n'
    expect(parseXfailEntries(content)).toEqual([{ pattern: 'some-pattern', reason: 'listed in xfail list' }])
  })

  it('preserves newlines in multi-line reason text', () => {
    const content = '# pattern\nline one\nline two'
    expect(parseXfailEntries(content)).toEqual([{ pattern: 'pattern', reason: 'line one\nline two' }])
  })

  it('skips blank lines in reason', () => {
    const content = '# pattern\nfirst\n\nsecond'
    expect(parseXfailEntries(content)).toEqual([{ pattern: 'pattern', reason: 'first\nsecond' }])
  })

  it('trims whitespace from headings', () => {
    const content = '#   spaced-pattern  \nreason'
    expect(parseXfailEntries(content)).toEqual([{ pattern: 'spaced-pattern', reason: 'reason' }])
  })

  it('returns empty array for content with no headings', () => {
    expect(parseXfailEntries('just some text\nno headings here')).toEqual([])
  })

  it('returns empty array for empty string', () => {
    expect(parseXfailEntries('')).toEqual([])
  })

  it('ignores non-h1 headings', () => {
    const content = '## h2 heading\ntext\n### h3 heading\nmore text'
    expect(parseXfailEntries(content)).toEqual([])
  })
})

describe('matchPattern', () => {
  describe('prefix matching (directory/file patterns)', () => {
    it('matches when testId starts with pattern', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'auth/')).toBe(true)
    })

    it('matches exact file path', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'auth/login.spec.ts')).toBe(true)
    })

    it('does not match unrelated prefix', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'settings/')).toBe(false)
    })
  })

  describe('title matching with " > " (no file prefix)', () => {
    it('matches exact full testId', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'auth/login.spec.ts > login > works')).toBe(true)
    })

    it('matches as suffix (endsWith)', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'login > works')).toBe(true)
    })

    it('requires segment boundary for suffix match', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'ogin > works')).toBe(false)
    })

    it('does not match unrelated title', () => {
      expect(matchPattern('auth/login.spec.ts > login > works', 'login > fails')).toBe(false)
    })
  })

  describe('file:title syntax ("file.ts: title")', () => {
    it('matches exact file + full title path', () => {
      expect(
        matchPattern(
          'auth/login.spec.ts > login form > should succeed',
          'auth/login.spec.ts: login form > should succeed'
        )
      ).toBe(true)
    })

    it('matches file + title suffix', () => {
      expect(
        matchPattern('auth/login.spec.ts > login form > should succeed', 'auth/login.spec.ts: should succeed')
      ).toBe(true)
    })

    it('does not match wrong file with correct title', () => {
      expect(
        matchPattern('auth/login.spec.ts > login form > should succeed', 'settings/profile.spec.ts: should succeed')
      ).toBe(false)
    })

    it('does not match correct file with wrong title', () => {
      expect(matchPattern('auth/login.spec.ts > login form > should succeed', 'auth/login.spec.ts: should fail')).toBe(
        false
      )
    })

    it('scopes match to the specified file (fixes cross-file ambiguity)', () => {
      const testIdA = 'auth/login.spec.ts > login form > should succeed'
      const testIdB = 'other/login.spec.ts > login form > should succeed'
      const pattern = 'auth/login.spec.ts: login form > should succeed'

      expect(matchPattern(testIdA, pattern)).toBe(true)
      expect(matchPattern(testIdB, pattern)).toBe(false)
    })

    it('works with .js extension', () => {
      expect(matchPattern('tests/foo.js > bar > baz', 'tests/foo.js: bar > baz')).toBe(true)
    })

    it('works with bare filename (no directory)', () => {
      expect(matchPattern('login.spec.ts > form > submit', 'login.spec.ts: form > submit')).toBe(true)
    })

    it('treats empty title after colon as file prefix match', () => {
      expect(matchPattern('auth/login.spec.ts > form > submit', 'auth/login.spec.ts: ')).toBe(true)
    })

    it('does not treat colon in non-file context as file:title syntax', () => {
      expect(matchPattern('file.spec.ts > API status: 200 > works', 'API status: 200 > works')).toBe(true)
    })
  })
})
