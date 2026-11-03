import { describe, expect, it } from 'vitest'

import { renderNodeIcon } from './renderNodeIcon'
import type { NodeIconVariant } from './renderNodeIcon'
import { renderStepIcon } from './renderStepIcon'
import type { StepIconVariant } from './renderStepIcon'

describe('legacy node icon renderer exports', () => {
  it('re-exports the step renderer', () => {
    expect(renderNodeIcon).toBe(renderStepIcon)
  })

  it('preserves the legacy icon variant type', () => {
    const nodeVariant: NodeIconVariant = 'header'
    const stepVariant: StepIconVariant = nodeVariant

    expect(stepVariant).toBe('header')
  })
})
