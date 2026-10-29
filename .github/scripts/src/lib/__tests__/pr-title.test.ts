import { describe, it, expect } from 'vitest'
import { JIRA_HOSTS } from '../jira.js'
import { checkPrTitle, normalizePrTitle } from '../pr-title.js'

describe('checkPrTitle', () => {
  it.each([
    'fix(auth): handle expired tokens',
    'fix: handle expired tokens',
    'feat(api)!: drop v1 endpoints',
    'chore(tekton,tests): pin pipeline bundle',
    'chore(visual-regression): update baselines',
    'revert: undo router migration',
    'fix: patch CVE-2026-59869 in seroval',
    'docs: document AAP-2.5 compatibility',
  ])('accepts %s', (title) => {
    expect(checkPrTitle(title)).toEqual({ errors: [], warnings: [] })
  })

  it.each([
    ['fix[auth]: handle expired tokens', 'Square brackets'],
    ['[UI] Migrate Users & Groups forms', 'Square brackets'],
    ['fix(AAP-88572): handle expired tokens', 'Jira references'],
    ['fix: handle expired tokens (ANSTRAT-1934)', 'Jira references'],
    [`fix: handle https://${JIRA_HOSTS[0]}/browse/AAP-1 tokens`, 'Jira references'],
    ['fix(): handle expired tokens', 'scope is empty'],
    ['fix handle expired tokens', 'must match'],
    ['fix(e2e):Unskip tests', 'must match'],
    ['chore(ci) Pin GHA to full SHA', 'must match'],
    ['Fix: handle expired tokens', 'must match'],
    ['fix/frontend containerfile hardening', 'must match'],
    ['bugfix: handle expired tokens', 'Unknown type `bugfix`'],
  ])('rejects %s', (title, expectedError) => {
    expect(checkPrTitle(title).errors.join('\n')).toContain(expectedError)
  })

  it('warns about style without failing', () => {
    const { errors, warnings } = checkPrTitle(`fix(auth): Handle expired tokens ${'x'.repeat(60)}.`)

    expect(errors).toEqual([])
    expect(warnings).toHaveLength(3)
  })

  it.each([
    ['fix[auth]: handle expired tokens', 'fix(auth): handle expired tokens'],
    ['[AAP-123] fix: handle expired tokens', 'fix: handle expired tokens'],
    ['fix(AAP-88572): handle expired tokens', 'fix: handle expired tokens'],
    ['fix(): handle expired tokens', 'fix: handle expired tokens'],
    ['Fix(e2e):unskip tests', 'fix(e2e): unskip tests'],
  ])('suggests a corrected title for %s', (title, suggestion) => {
    expect(checkPrTitle(title).suggestion).toBe(suggestion)
  })

  it('offers no suggestion when normalization cannot produce a valid title', () => {
    expect(checkPrTitle('[UX]: UX Skill - clarify builder copy').suggestion).toBeUndefined()
  })
})

describe('normalizePrTitle', () => {
  it.each([
    ['  fix:   handle   tokens ', 'fix: handle tokens'],
    ['fix(auth): handle tokens (AAP-123)', 'fix(auth): handle tokens'],
    ['fix: AAP-123 handle tokens', 'fix: handle tokens'],
    ['chore(AAP-1, AAP-2): bump deps', 'chore: bump deps'],
    ['fix(auth): handle tokens', 'fix(auth): handle tokens'],
  ])('normalizes %s', (title, expected) => {
    expect(normalizePrTitle(title)).toBe(expected)
  })
})
