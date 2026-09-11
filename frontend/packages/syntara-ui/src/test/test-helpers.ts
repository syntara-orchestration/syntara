import type { Activity } from '@syntara/contracts'
import { expect } from 'vitest'

/** Options for creating a condition fixture with flexible config */
type ConditionOverrides = {
  id?: string
  name?: string
  condition?: string
}

/**
 * Creates a v2 condition Activity fixture for testing.
 * V2: condition expression is in parameters.condition, no then/else arrays.
 */
export const makeCondition = (overrides: ConditionOverrides = {}): Activity => ({
  type: 'condition',
  id: overrides.id ?? 'C1',
  name: overrides.name ?? 'Condition',
  parameters: {
    condition: overrides.condition ?? 'x > 10',
  },
})

/**
 * Typed wrapper for vitest's `expect.stringContaining` asymmetric matcher.
 * Vitest types the matcher as `any`; this keeps call-site object literals type-safe.
 */
export function expectStringContaining(expected: string): string {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matchers are typed as any
  const matcher: string = expect.stringContaining(expected)
  return matcher
}
