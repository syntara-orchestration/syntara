import { describe, expect, it } from 'vitest'

import { formResponsesReducer, type FormResponsesAction } from './formResponsesReducer'

describe('formResponsesReducer', () => {
  it('returns the same state for unknown actions', () => {
    const state = { expandedRows: new Set(['fp-1']) }
    const unknownAction = { type: 'UNKNOWN' } as unknown as FormResponsesAction

    expect(formResponsesReducer(state, unknownAction)).toBe(state)
  })

  it('replaces expanded rows when SET_EXPANDED_ROWS is dispatched', () => {
    const state = { expandedRows: new Set(['fp-1']) }
    const next = new Set(['fp-2'])

    expect(formResponsesReducer(state, { type: 'SET_EXPANDED_ROWS', payload: next })).toEqual({
      expandedRows: next,
    })
  })

  it('adds and removes rows when TOGGLE_ROW is dispatched', () => {
    const state = { expandedRows: new Set(['fp-1']) }

    const expanded = formResponsesReducer(state, { type: 'TOGGLE_ROW', payload: 'fp-2' })
    expect(expanded.expandedRows.has('fp-1')).toBe(true)
    expect(expanded.expandedRows.has('fp-2')).toBe(true)

    const collapsed = formResponsesReducer(expanded, { type: 'TOGGLE_ROW', payload: 'fp-1' })
    expect(collapsed.expandedRows.has('fp-1')).toBe(false)
    expect(collapsed.expandedRows.has('fp-2')).toBe(true)
  })
})
