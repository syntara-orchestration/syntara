import { describe, expect, it } from 'vitest'

import { approvalsReducer, type ApprovalsAction } from './approvalsReducer'

describe('approvalsReducer', () => {
  it('returns the same state for unknown actions', () => {
    const state = { expandedRows: new Set(['a1']) }
    const unknownAction = { type: 'UNKNOWN' } as unknown as ApprovalsAction

    expect(approvalsReducer(state, unknownAction)).toBe(state)
  })

  it('replaces expanded rows when SET_EXPANDED_ROWS is dispatched', () => {
    const state = { expandedRows: new Set(['a1']) }
    const next = new Set(['a2', 'a3'])

    expect(approvalsReducer(state, { type: 'SET_EXPANDED_ROWS', payload: next })).toEqual({
      expandedRows: next,
    })
  })

  it('adds and removes rows when TOGGLE_ROW is dispatched', () => {
    const state = { expandedRows: new Set(['a1']) }

    const expanded = approvalsReducer(state, { type: 'TOGGLE_ROW', payload: 'a2' })
    expect(expanded.expandedRows.has('a1')).toBe(true)
    expect(expanded.expandedRows.has('a2')).toBe(true)

    const collapsed = approvalsReducer(expanded, { type: 'TOGGLE_ROW', payload: 'a1' })
    expect(collapsed.expandedRows.has('a1')).toBe(false)
    expect(collapsed.expandedRows.has('a2')).toBe(true)
  })
})
