import type { TestInfo } from '@playwright/test'
import { describe, expect, it } from 'vitest'

import {
  buildTestId,
  formatUnexpectedXfailPasses,
  formatXfailRules,
  hasNonXfailFailure,
  matchPattern,
  parseXfailEntries,
  softenFailedRunForXfailPasses,
  unexpectedXfailPass,
  xfailFailDescription,
  xfailSourceFromEnv,
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

describe('xfailSourceFromEnv', () => {
  it('returns null when the env var is unset', () => {
    expect(xfailSourceFromEnv({})).toBeNull()
  })

  it('appends playwright.md to a base ending in a slash', () => {
    expect(xfailSourceFromEnv({ SYNTARA_XFAIL_SOURCE: 'https://example.com/ci/' })).toBe(
      'https://example.com/ci/playwright.md'
    )
  })

  it('inserts a slash when the base does not end in one', () => {
    expect(xfailSourceFromEnv({ SYNTARA_XFAIL_SOURCE: 'https://example.com/ci' })).toBe(
      'https://example.com/ci/playwright.md'
    )
  })
})

describe('formatXfailRules', () => {
  it('lists every rule with its reason', () => {
    const lines = formatXfailRules(
      [
        { pattern: 'auth/login.spec.ts', reason: 'flaky' },
        { pattern: 'settings.spec.ts > saves', reason: 'known bad' },
      ],
      'https://example.com/ci/playwright.md'
    )
    expect(lines[0]).toBe('xfail: 2 rule(s) from https://example.com/ci/playwright.md:')
    expect(lines).toContain('  - auth/login.spec.ts — flaky')
    expect(lines).toContain('  - settings.spec.ts > saves — known bad')
  })

  it('collapses multi-line reasons onto one line', () => {
    const lines = formatXfailRules([{ pattern: 'a.spec.ts', reason: 'line one\nline two' }], 'src')
    expect(lines).toContain('  - a.spec.ts — line one line two')
  })

  it('reports when no rules were loaded', () => {
    expect(formatXfailRules([], 'src')).toEqual(['xfail: no rules loaded from src'])
  })
})

describe('xfailFailDescription', () => {
  it('prefixes the reason so the reporter can distinguish our xfails', () => {
    expect(xfailFailDescription('flaky under load')).toBe('xfail: flaky under load')
  })
})

describe('unexpectedXfailPass', () => {
  const listedPass = {
    expectedStatus: 'failed',
    status: 'passed',
    titlePath: ['auth/login.spec.ts', 'login form', 'should succeed'],
    annotations: [{ type: 'fail', description: 'xfail: flaky under load' }],
  }

  it('returns the test id and reason for a listed xfail that passed', () => {
    expect(unexpectedXfailPass(listedPass)).toEqual({
      testId: 'auth/login.spec.ts > login form > should succeed',
      reason: 'flaky under load',
    })
  })

  it('ignores a listed xfail that actually failed', () => {
    expect(unexpectedXfailPass({ ...listedPass, status: 'failed' })).toBeNull()
  })

  it('ignores a passing test that was not marked fail', () => {
    expect(
      unexpectedXfailPass({
        ...listedPass,
        expectedStatus: 'passed',
        annotations: [],
      })
    ).toBeNull()
  })

  it('ignores test.fail() / quarantine that is not from the xfail list', () => {
    expect(
      unexpectedXfailPass({
        ...listedPass,
        annotations: [{ type: 'fail', description: 'known broken' }],
      })
    ).toBeNull()
  })

  it('uses the default reason when the annotation has no text after the prefix', () => {
    expect(
      unexpectedXfailPass({
        ...listedPass,
        annotations: [{ type: 'fail', description: 'xfail:' }],
      })
    ).toEqual({
      testId: 'auth/login.spec.ts > login form > should succeed',
      reason: 'listed in xfail list',
    })
  })

  it('drops empty titlePath segments', () => {
    expect(
      unexpectedXfailPass({
        ...listedPass,
        titlePath: ['', 'auth/login.spec.ts', 'should succeed'],
      })?.testId
    ).toBe('auth/login.spec.ts > should succeed')
  })
})

describe('formatUnexpectedXfailPasses', () => {
  it('returns nothing when no listed tests passed', () => {
    expect(formatUnexpectedXfailPasses([])).toEqual([])
  })

  it('lists every unexpected pass with its reason', () => {
    const lines = formatUnexpectedXfailPasses([
      { testId: 'auth/login.spec.ts > should succeed', reason: 'flaky' },
      { testId: 'settings.spec.ts > saves', reason: 'line one\nline two' },
    ])
    expect(lines[0]).toBe('xfail: 2 listed test(s) passed (remove from playwright.md):')
    expect(lines).toContain('  - auth/login.spec.ts > should succeed — flaky')
    expect(lines).toContain('  - settings.spec.ts > saves — line one line two')
  })
})

describe('softenFailedRunForXfailPasses', () => {
  const xpass = {
    expectedStatus: 'failed',
    status: 'passed',
    titlePath: ['a.spec.ts', 'listed'],
    annotations: [{ type: 'fail', description: 'xfail: flaky' }],
  }
  const expectedFail = { ...xpass, status: 'failed' }
  const green = {
    expectedStatus: 'passed',
    status: 'passed',
    titlePath: ['a.spec.ts', 'control'],
    annotations: [],
  }
  const realFail = {
    expectedStatus: 'passed',
    status: 'failed',
    titlePath: ['a.spec.ts', 'unlisted'],
    annotations: [],
  }

  it('does not treat an xfail that actually failed as blocking', () => {
    expect(hasNonXfailFailure([expectedFail, green])).toBe(false)
  })

  it('treats an unlisted failure as blocking', () => {
    expect(hasNonXfailFailure([xpass, realFail])).toBe(true)
  })

  it('turns a failed run green when only listed xfails passed', () => {
    expect(softenFailedRunForXfailPasses('failed', [xpass, green])).toBe('passed')
  })

  it('leaves the run failed when a real test also failed', () => {
    expect(softenFailedRunForXfailPasses('failed', [xpass, realFail])).toBeUndefined()
  })

  it('does not change a run that already passed', () => {
    expect(softenFailedRunForXfailPasses('passed', [green])).toBeUndefined()
  })
})

describe('buildTestId', () => {
  // testInfo.titlePath already starts with the testDir-relative spec path
  // (verified against Playwright: e.g. ['sub/foo.spec.ts', 'describe', 'test']).
  const asTestInfo = (titlePath: string[]): Pick<TestInfo, 'titlePath'> =>
    ({ titlePath }) as Pick<TestInfo, 'titlePath'>

  it('joins the titlePath without duplicating the spec path', () => {
    // Regression: buildTestId used to prepend testInfo.file, yielding
    // "sub/foo.spec.ts > sub/foo.spec.ts > ...". The id must contain the spec
    // path exactly once so exact-match patterns work.
    const id = buildTestId(asTestInfo(['sub/foo.spec.ts', 'login form', 'should succeed']))
    expect(id).toBe('sub/foo.spec.ts > login form > should succeed')
  })

  it('handles a spec with no describe block', () => {
    expect(buildTestId(asTestInfo(['foo.spec.ts', 'works']))).toBe('foo.spec.ts > works')
  })

  it('drops empty segments', () => {
    expect(buildTestId(asTestInfo(['foo.spec.ts', '', 'works']))).toBe('foo.spec.ts > works')
  })

  it('produces an id an exact file:title pattern matches', () => {
    const id = buildTestId(asTestInfo(['auth/login.spec.ts', 'login form', 'should succeed']))
    expect(matchPattern(id, 'auth/login.spec.ts: login form > should succeed')).toBe(true)
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
