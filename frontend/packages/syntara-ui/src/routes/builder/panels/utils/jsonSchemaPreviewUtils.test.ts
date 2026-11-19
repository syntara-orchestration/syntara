import { describe, expect, it } from 'vitest'

import { mapJsonSchemaPropertyType, mapJsonSchemaType } from './jsonSchemaPreviewUtils'

describe('mapJsonSchemaType', () => {
  it.each([
    ['string', 'string'],
    ['integer', 'number'],
    ['unknown-type', 'unknown'],
    [undefined, 'unknown'],
  ] as const)('maps %s to %s', (schemaType, expected) => {
    expect(mapJsonSchemaType(schemaType)).toBe(expected)
  })
})

describe('mapJsonSchemaPropertyType', () => {
  it.each([
    ['required checkbox', { const: true }, 'boolean'],
    ['optional checkbox', { const: false }, 'boolean'],
    ['string property', { type: 'string' }, 'string'],
    ['integer property', { type: 'integer' }, 'number'],
    ['nullable union', { type: ['number', 'null'] }, 'number'],
    ['all-null union', { type: ['null', 'null'] }, 'unknown'],
    ['array property', { type: 'array', items: { type: 'string' } }, 'array'],
    ['non-string type keyword', { type: 1 }, 'unknown'],
    ['missing type', {}, 'unknown'],
  ] as const)('maps %s', (_label, property, expected) => {
    expect(mapJsonSchemaPropertyType(property)).toBe(expected)
  })
})
