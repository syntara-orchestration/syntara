import { describe, expect, it } from 'vitest'

import { computeProjectTabState } from './projectDetailTabs'

describe('computeProjectTabState', () => {
  it('keeps only Details visible while permissions load', () => {
    expect(computeProjectTabState(false, false, true, 'details')).toEqual({
      visibleTabs: ['details'],
      urlValidTabs: ['details'],
    })
  })

  it('preserves a deep-linked workflows tab in urlValidTabs while permissions load', () => {
    expect(computeProjectTabState(false, false, true, 'workflows')).toEqual({
      visibleTabs: ['details'],
      urlValidTabs: ['details', 'workflows'],
    })
  })

  it('preserves a deep-linked assignments tab in urlValidTabs while permissions load', () => {
    expect(computeProjectTabState(false, false, true, 'role-assignments')).toEqual({
      visibleTabs: ['details'],
      urlValidTabs: ['details', 'role-assignments'],
    })
  })

  it('filters denied tabs once permissions resolve', () => {
    expect(computeProjectTabState(false, true, false, 'workflows')).toEqual({
      visibleTabs: ['details', 'role-assignments'],
      urlValidTabs: ['details', 'role-assignments'],
    })
  })

  it('shows granted tabs once permissions resolve', () => {
    expect(computeProjectTabState(true, true, false, 'workflows')).toEqual({
      visibleTabs: ['details', 'workflows', 'role-assignments'],
      urlValidTabs: ['details', 'workflows', 'role-assignments'],
    })
  })
})
