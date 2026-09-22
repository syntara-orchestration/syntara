import { describe, expect, it } from 'vitest'

import { labelToValueName, slugifyLabelToValueNameBase } from './labelToValueName'

describe('slugifyLabelToValueNameBase', () => {
  it('converts spaces to underscores', () => {
    expect(slugifyLabelToValueNameBase('Contact Email')).toBe('contact_email')
  })

  it('prefixes names that start with a digit', () => {
    expect(slugifyLabelToValueNameBase('2026 plan')).toBe('field_2026_plan')
  })

  it('returns field for empty labels', () => {
    expect(slugifyLabelToValueNameBase('   ')).toBe('field')
  })

  it('slugifies punctuation and collapses separators', () => {
    expect(slugifyLabelToValueNameBase('foo-bar / baz')).toBe('foo_bar_baz')
    expect(slugifyLabelToValueNameBase('a   b')).toBe('a_b')
  })

  it('strips trailing underscores', () => {
    expect(slugifyLabelToValueNameBase('name___')).toBe('name')
  })
})

describe('labelToValueName', () => {
  it('deduplicates against taken names', () => {
    expect(labelToValueName('Name', ['name'])).toBe('name_2')
  })

  it('returns base when not taken', () => {
    expect(labelToValueName('Priority', [])).toBe('priority')
  })

  it('allocates higher suffixes when lower ones are taken', () => {
    expect(labelToValueName('Tier', ['tier', 'tier_2'])).toBe('tier_3')
  })
})
