import { describe, expect, it } from 'vitest'

import { getAddNodePanelColor, getNodeTypeColor, NODE_TYPE_COLORS } from './nodeTypeColors'
import type { NodeTypeColorKey } from './nodeTypeColors'
import { getAddStepPanelColor, getStepTypeColor, STEP_TYPE_COLORS } from './stepTypeColors'
import type { StepTypeColorKey } from './stepTypeColors'

describe('legacy node color exports', () => {
  it('re-exports the step colors and helpers', () => {
    expect(NODE_TYPE_COLORS).toBe(STEP_TYPE_COLORS)
    expect(getNodeTypeColor).toBe(getStepTypeColor)
    expect(getAddNodePanelColor).toBe(getAddStepPanelColor)
  })

  it('preserves the legacy color key type', () => {
    const nodeColorKey: NodeTypeColorKey = 'trigger'
    const stepColorKey: StepTypeColorKey = nodeColorKey

    expect(stepColorKey).toBe('trigger')
  })
})
