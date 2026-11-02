import { describe, expect, it } from 'vitest'

import { getNodeSelectors } from './getNodeSelectors'

describe('getNodeSelectors', () => {
  it('returns kubernetes node_selectors', () => {
    expect(
      getNodeSelectors({
        type: 'kubernetes',
        namespace: 'syntara-workers',
        node_selectors: ['workload=automation'],
      })
    ).toEqual(['workload=automation'])
  })

  it('returns an empty list for RHEL placement', () => {
    expect(getNodeSelectors({ type: 'rhel' })).toEqual([])
  })

  it('returns an empty list when node_selectors is omitted', () => {
    expect(getNodeSelectors({ type: 'kubernetes', namespace: 'ns' })).toEqual([])
  })
})
