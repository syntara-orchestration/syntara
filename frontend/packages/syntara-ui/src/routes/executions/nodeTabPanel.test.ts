import { describe, expect, it } from 'vitest'

import { nodeTabPanelAttrs, nodeTabPanelId } from './nodeTabPanel'

describe('nodeTabPanelId', () => {
  it('suffixes the base id with -panel', () => {
    expect(nodeTabPanelId('node-7')).toBe('node-7-panel')
  })
})

describe('nodeTabPanelAttrs', () => {
  it('returns no attributes when the node has no tabs', () => {
    expect(nodeTabPanelAttrs(false, 'node-7', 'io')).toEqual({})
  })

  it('returns tabpanel ARIA attributes labelled by the active tab when the node has tabs', () => {
    expect(nodeTabPanelAttrs(true, 'node-7', 'agent-steps')).toEqual({
      id: 'node-7-panel',
      role: 'tabpanel',
      'aria-label': 'agent-steps',
    })
  })

  it('reuses nodeTabPanelId for the panel id', () => {
    const attrs = nodeTabPanelAttrs(true, 'base', 'io') as { id: string }
    expect(attrs.id).toBe(nodeTabPanelId('base'))
  })
})
