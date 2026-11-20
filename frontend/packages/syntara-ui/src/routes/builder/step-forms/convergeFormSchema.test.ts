import { describe, expect, it } from 'vitest'

import { convergeFormSchema } from './convergeFormSchema'

describe('convergeFormSchema', () => {
  it('accepts valid form data with strategy all', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'all',
    })
    expect(result.success).toBe(true)
  })

  it('accepts valid form data with strategy any and required path fields', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'any',
      requiredPathCount: 2,
    })
    expect(result.success).toBe(true)
  })

  it('accepts valid form data with settings', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'all',
      settings: { continue_on_failure: true, timeout: 3600 },
    })
    expect(result.success).toBe(true)
  })

  it('rejects invalid strategy', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: '',
    })
    expect(result.success).toBe(false)
  })

  it('accepts strategy any without required path count (permissive)', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'any',
    })
    expect(result.success).toBe(true)
  })

  it('rejects strategy any with required path count of 0 (field-level validation)', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'any',
      requiredPathCount: 0,
    })
    expect(result.success).toBe(false)
  })

  it('rejects negative requiredPathCount', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'any',
      requiredPathCount: -1,
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(
        result.error.issues.some(
          (i) =>
            i.message === 'Required path count must be a whole number greater than 0' &&
            (i.path?.includes('requiredPathCount') ?? false)
        )
      ).toBe(true)
    }
  })

  it('rejects decimal requiredPathCount', () => {
    const result = convergeFormSchema.safeParse({
      name: 'Converge',
      strategy: 'any',
      requiredPathCount: 2.5,
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(
        result.error.issues.some(
          (i) =>
            i.message === 'Required path count must be a whole number greater than 0' &&
            (i.path?.includes('requiredPathCount') ?? false)
        )
      ).toBe(true)
    }
  })
})
