import { describe, expect, it } from 'vitest'

import {
  isSynDynamicFormSelectOption,
  mapDynamicOptionsFromRecords,
  normalizeDynamicOptionsResult,
} from './mapDynamicOptionsFromRecords'

const dynamicConfig = {
  source: 'dynamic' as const,
  expression: '${nodes.x}',
  label_key: 'name',
  value_key: 'id',
}

describe('mapDynamicOptionsFromRecords', () => {
  it('maps records using label_key and value_key', () => {
    const options = mapDynamicOptionsFromRecords(
      [
        { name: 'US East', id: 'use1' },
        { name: 'EU West', id: 'euw1' },
      ],
      dynamicConfig
    )
    expect(options).toEqual([
      { label: 'US East', value: 'use1' },
      { label: 'EU West', value: 'euw1' },
    ])
  })

  it('uses display_label and value as defaults', () => {
    const options = mapDynamicOptionsFromRecords([{ display_label: 'Low', value: 'low' }], {
      source: 'dynamic',
      expression: '${x}',
    })
    expect(options).toEqual([{ label: 'Low', value: 'low' }])
  })

  it('passes through pre-built select options', () => {
    const built = [{ label: 'A', value: 'a' }]
    expect(mapDynamicOptionsFromRecords(built, dynamicConfig)).toEqual(built)
  })
})

describe('normalizeDynamicOptionsResult', () => {
  it('returns pre-built options when every item is normalized', () => {
    const built = [{ label: 'A', value: 1 }]
    expect(normalizeDynamicOptionsResult(built, dynamicConfig)).toEqual(built)
    expect(isSynDynamicFormSelectOption(built[0])).toBe(true)
  })

  it('maps raw records when items are not pre-built options', () => {
    const raw = [{ name: 'X', id: 42 }]
    expect(normalizeDynamicOptionsResult(raw, dynamicConfig)).toEqual([{ label: 'X', value: 42 }])
  })
})
