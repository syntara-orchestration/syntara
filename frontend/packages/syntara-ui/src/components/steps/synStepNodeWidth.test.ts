import { describe, expect, it } from 'vitest'

import { getSynStepNodeWidth, SYN_STEP_DEFAULT_NODE_WIDTH } from './synStepNodeWidth'

describe('getSynStepNodeWidth', () => {
  it('uses the fixed default width for every step', () => {
    expect(getSynStepNodeWidth()).toBe(SYN_STEP_DEFAULT_NODE_WIDTH)
    expect(SYN_STEP_DEFAULT_NODE_WIDTH).toBe(300)
  })
})
