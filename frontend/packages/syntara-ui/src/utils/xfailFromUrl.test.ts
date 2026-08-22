import { describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_XFAIL_SOURCE,
  applyListedXfail,
  matchPattern,
  parseXfailEntries,
  resolveXfailSource,
  toXfailMarkdownUrl,
  xfailMode,
} from '../../e2e/xfailFromUrl'

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

    it('matches Currents playwright.md file:title headings', () => {
      expect(
        matchPattern(
          'workflows/approvals.spec.ts > user cancels batch approval without API call',
          'workflows/approvals.spec.ts: user cancels batch approval without API call'
        )
      ).toBe(true)
      expect(
        matchPattern(
          'workflows/approvals.spec.ts > workflows/approvals.spec.ts > user performs batch rejection operations',
          'workflows/approvals.spec.ts: user performs batch rejection operations'
        )
      ).toBe(true)
    })
  })
})

describe('resolveXfailSource', () => {
  it('defaults to syntara-ci in CI when unset', () => {
    expect(resolveXfailSource({ CI: 'true' })).toBe(DEFAULT_XFAIL_SOURCE)
  })

  it('does not default outside CI', () => {
    expect(resolveXfailSource({})).toBeUndefined()
  })

  it('honors an explicit source in CI', () => {
    expect(resolveXfailSource({ CI: 'true', SYNTARA_XFAIL_SOURCE: 'https://example.invalid/' })).toBe(
      'https://example.invalid/'
    )
  })

  it('treats empty SYNTARA_XFAIL_SOURCE as disabled even in CI', () => {
    expect(resolveXfailSource({ CI: 'true', SYNTARA_XFAIL_SOURCE: '' })).toBeUndefined()
    expect(resolveXfailSource({ CI: 'true', SYNTARA_XFAIL_SOURCE: '   ' })).toBeUndefined()
  })

  it('does not default when CI is explicitly false', () => {
    expect(resolveXfailSource({ CI: 'false' })).toBeUndefined()
    expect(resolveXfailSource({ CI: '0' })).toBeUndefined()
  })
})

describe('toXfailMarkdownUrl', () => {
  it('appends playwright.md to a trailing-slash base', () => {
    expect(toXfailMarkdownUrl(DEFAULT_XFAIL_SOURCE, 'playwright.md')).toBe(`${DEFAULT_XFAIL_SOURCE}playwright.md`)
  })

  it('inserts a slash when the base has none', () => {
    expect(toXfailMarkdownUrl('https://example.invalid/ci', 'playwright.md')).toBe(
      'https://example.invalid/ci/playwright.md'
    )
  })
})

describe('xfailMode', () => {
  it('uses expected-fail when Currents credentials are present', () => {
    expect(
      xfailMode({
        CURRENTS_PROJECT_ID: 'proj',
        CURRENTS_RECORD_KEY: 'key',
      })
    ).toBe('fail')
    expect(xfailMode({ CURRENTS_API_KEY: 'api' })).toBe('fail')
  })

  it('skips when Currents credentials are missing or blank', () => {
    expect(xfailMode({})).toBe('skip')
    expect(
      xfailMode({
        CURRENTS_PROJECT_ID: '',
        CURRENTS_RECORD_KEY: '  ',
        CURRENTS_API_KEY: '',
      })
    ).toBe('skip')
  })
})

describe('applyListedXfail', () => {
  it('calls skip for skip mode', () => {
    const skip = vi.fn()
    const fail = vi.fn()
    applyListedXfail({ skip, fail }, { pattern: 'foo.spec.ts', reason: 'flaky' }, 'skip')
    expect(skip).toHaveBeenCalledWith(true, 'xfail: flaky')
    expect(fail).not.toHaveBeenCalled()
  })

  it('calls fail for fail mode', () => {
    const skip = vi.fn()
    const fail = vi.fn()
    applyListedXfail({ skip, fail }, { pattern: 'foo.spec.ts', reason: 'flaky' }, 'fail')
    expect(fail).toHaveBeenCalledWith(true, 'xfail: flaky')
    expect(skip).not.toHaveBeenCalled()
  })
})
