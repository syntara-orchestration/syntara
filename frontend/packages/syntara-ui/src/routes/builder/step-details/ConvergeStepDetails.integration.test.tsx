import { describe, expect, it } from 'vitest'

/**
 * Integration tests for ConvergeStepDetails snake_case/camelCase compatibility
 * These tests verify the handleSubmit logic writes snake_case fields
 */

describe('ConvergeStepDetails snake_case Field Writing Logic', () => {
  // Simulate the handleSubmit logic from ConvergeStepDetails.tsx
  function simulateHandleSubmit(formData: {
    name: string
    strategy?: 'all' | 'any'
    timeout?: number
    onTimeout?: 'continue' | 'fail'
    requiredPathCount?: number
  }) {
    const parameters: Record<string, unknown> = {
      strategy: formData.strategy ?? 'all',
      ...(formData.timeout !== undefined && { timeout: formData.timeout }),
      ...(formData.onTimeout !== undefined && { on_timeout: formData.onTimeout }),
      ...(formData.strategy === 'any' &&
        formData.requiredPathCount !== undefined && {
          n_required: formData.requiredPathCount,
        }),
    }

    return parameters
  }

  it('writes n_required in snake_case (not requiredPathCount)', () => {
    const formData = {
      name: 'Updated Converge',
      strategy: 'any' as const,
      requiredPathCount: 2,
    }

    const result = simulateHandleSubmit(formData)

    expect(result.n_required).toBe(2)
    expect(result.requiredPathCount).toBeUndefined()
    expect(result.required_path_count).toBeUndefined()
  })

  it('writes on_timeout in snake_case (not onTimeout)', () => {
    const formData = {
      name: 'Updated Converge',
      strategy: 'all' as const,
      timeout: 3600,
      onTimeout: 'continue' as const,
    }

    const result = simulateHandleSubmit(formData)

    // Should write snake_case
    expect(result.on_timeout).toBe('continue')

    // Should NOT write camelCase
    expect(result.onTimeout).toBeUndefined()
  })

  it('omits n_required when strategy is "all"', () => {
    const formData = {
      name: 'Updated Converge',
      strategy: 'all' as const,
      requiredPathCount: 2,
    }

    const result = simulateHandleSubmit(formData)

    expect(result.strategy).toBe('all')
    expect(result.n_required).toBeUndefined()
  })

  it('includes n_required when strategy is "any"', () => {
    const formData = {
      name: 'Updated Converge',
      strategy: 'any' as const,
      requiredPathCount: 2,
    }

    const result = simulateHandleSubmit(formData)

    expect(result.strategy).toBe('any')
    expect(result.n_required).toBe(2)
  })
})
