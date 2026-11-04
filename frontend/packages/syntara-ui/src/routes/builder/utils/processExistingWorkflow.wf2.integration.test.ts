import { describe, expect, it } from 'vitest'

import { convertV2Definition } from './processExistingWorkflow'

/** Regression: WF2-like definitions must produce edges so the canvas can initialize. */
describe('convertV2Definition WF2 shape', () => {
  it('maps trigger activity id to trigger-0 and keeps edges', () => {
    const triggerId = 'activity_3cab9470_07fb_4149_a894_22c4486b21e5'
    const formId = 'activity_a20ea708_78d1_4ba1_ac61_9bd223ff5ccd'
    const scriptId = 'activity_2092e94e_bd46_4aab_8b0e_6040e1276100'

    const nodes = [
      { id: scriptId, name: 'Script', type: 'script', parameters: {} },
      { id: formId, name: 'Form', type: 'form_prompt', parameters: {} },
      { id: 'activity_c5a66f38_3d45_43c5_8644_90e5575595c5', name: 'Script 2', type: 'script', parameters: {} },
    ]
    const v2Edges = [
      { from: triggerId, to: formId },
      { from: formId, to: scriptId, from_port: 'submitted' },
      { from: formId, to: 'activity_c5a66f38_3d45_43c5_8644_90e5575595c5', from_port: 'fallback' },
    ]
    const rawTriggers = [{ id: triggerId, type: 'manual_trigger', name: 'Manual' }]

    const { flattenedActivities, edges, triggers } = convertV2Definition(nodes, v2Edges, rawTriggers)

    expect(flattenedActivities).toHaveLength(3)
    expect(triggers).toHaveLength(1)
    expect(edges.length).toBeGreaterThan(0)
    expect(edges.some((e) => e.source === 'trigger-0' && e.target === formId)).toBe(true)
  })
})
