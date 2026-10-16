import { describe, expect, it } from 'vitest'

import { resolveFormPromptCssOverride } from './resolveFormPromptCssOverride'

describe('resolveFormPromptCssOverride', () => {
  it('returns undefined when override is missing or blank', () => {
    expect(resolveFormPromptCssOverride(undefined)).toBeUndefined()
    expect(resolveFormPromptCssOverride(null)).toBeUndefined()
    expect(resolveFormPromptCssOverride('')).toBeUndefined()
    expect(resolveFormPromptCssOverride('   \n\t')).toBeUndefined()
  })

  it('returns trimmed CSS when override has content', () => {
    expect(resolveFormPromptCssOverride('  .form-step-response-form { color: red; }  ')).toBe(
      '.form-step-response-form { color: red; }'
    )
  })
})
