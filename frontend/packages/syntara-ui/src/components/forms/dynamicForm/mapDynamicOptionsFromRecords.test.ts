import { describe, expect, it } from 'vitest'

import { mapDynamicOptionsFromRecords, normalizeDynamicOptionsResult } from './mapDynamicOptionsFromRecords'

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

  it('maps the configured display_label and value keys', () => {
    const options = mapDynamicOptionsFromRecords([{ display_label: 'Low', value: 'low' }], {
      source: 'dynamic',
      expression: '${x}',
      label_key: 'display_label',
      value_key: 'value',
    })
    expect(options).toEqual([{ label: 'Low', value: 'low' }])
  })

  it('uses configured keys even when records already look like select options', () => {
    const built = [{ label: 'A', value: 'a' }]
    expect(() => mapDynamicOptionsFromRecords(built, dynamicConfig)).toThrow(/key "name"/)
  })
})

describe('normalizeDynamicOptionsResult', () => {
  it('maps options using explicitly configured label and value keys', () => {
    const built = [{ label: 'A', value: 1 }]
    expect(
      normalizeDynamicOptionsResult(built, {
        source: 'dynamic',
        expression: '${nodes.x}',
        label_key: 'label',
        value_key: 'value',
      })
    ).toEqual(built)
  })

  it('maps raw records when items are not pre-built options', () => {
    const raw = [{ name: 'X', id: 42 }]
    expect(normalizeDynamicOptionsResult(raw, dynamicConfig)).toEqual([{ label: 'X', value: 42 }])
  })
})
