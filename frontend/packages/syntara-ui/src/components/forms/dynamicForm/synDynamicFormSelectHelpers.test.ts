import { describe, expect, it } from 'vitest'

import { getSelectedScalarValues, optionKey } from './synDynamicFormSelectHelpers'

describe('synDynamicFormSelectHelpers', () => {
  it('optionKey stringifies non-string scalars', () => {
    expect(optionKey(1)).toBe('1')
    expect(optionKey(true)).toBe('true')
  })

  it('getSelectedScalarValues filters multi-select to scalars', () => {
    expect(getSelectedScalarValues(['a', 1, null, true], true)).toEqual(['a', 1, true])
    expect(getSelectedScalarValues('nope', true)).toEqual([])
  })

  it('getSelectedScalarValues returns single scalar for dropdown', () => {
    expect(getSelectedScalarValues('east', false)).toEqual(['east'])
    expect(getSelectedScalarValues('', false)).toEqual([])
    expect(getSelectedScalarValues({ bad: true }, false)).toEqual([])
  })
})
