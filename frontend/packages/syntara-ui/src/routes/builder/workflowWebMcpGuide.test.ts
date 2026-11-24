import { describe, expect, it } from 'vitest'

import { WORKFLOW_GUIDE_TOPICS, getWorkflowGuide } from './workflowWebMcpGuide'

describe('getWorkflowGuide', () => {
  it('returns a section for each published topic', () => {
    for (const topic of WORKFLOW_GUIDE_TOPICS) {
      const guide = getWorkflowGuide(topic)
      expect(guide).not.toBeNull()
      if (guide) {
        expect(guide.title.length).toBeGreaterThan(0)
        expect(Array.isArray(guide.key_points)).toBe(true)
      }
    }
  })

  it('returns null for unknown or non-string topics', () => {
    expect(getWorkflowGuide('not-a-topic')).toBeNull()
    expect(getWorkflowGuide(undefined)).toBeNull()
    expect(getWorkflowGuide({ topic: 'overview' })).toBeNull()
  })
})
