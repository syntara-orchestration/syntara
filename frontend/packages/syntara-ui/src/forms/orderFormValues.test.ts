import type { FormDefinition } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { formFieldValueNames, orderValuesByFieldOrder } from './orderFormValues'

describe('formFieldValueNames', () => {
  it('returns value names in configured field order', () => {
    const definition: FormDefinition = {
      fields: [
        { type: 'text', value_name: 'deployment_name', label: 'Deployment' },
        { type: 'text', value_name: 'environment', label: 'Environment' },
        { type: 'text', value_name: 'id', label: 'ID' },
      ],
    }

    expect(formFieldValueNames(definition)).toEqual(['deployment_name', 'environment', 'id'])
  })
})

describe('orderValuesByFieldOrder', () => {
  it('moves configured keys into field order and keeps unknown keys in their relative order', () => {
    const values = {
      id: '42',
      extra_first: 'one',
      deployment_name: 'blue',
      environment: 'stage',
      extra_second: 'two',
    }

    const ordered = orderValuesByFieldOrder(values, ['deployment_name', 'environment', 'id'])

    expect(Object.keys(ordered)).toEqual(['deployment_name', 'environment', 'id', 'extra_first', 'extra_second'])
    expect(ordered).toEqual({
      deployment_name: 'blue',
      environment: 'stage',
      id: '42',
      extra_first: 'one',
      extra_second: 'two',
    })
  })

  it('returns the original reference when the order already matches', () => {
    const values = { deployment_name: 'blue', environment: 'stage', id: '42' }

    expect(orderValuesByFieldOrder(values, ['deployment_name', 'environment', 'id'])).toBe(values)
  })

  it('returns the original record for an empty order or record', () => {
    const values = { id: '42' }
    const empty: Record<string, string> = {}

    expect(orderValuesByFieldOrder(values, [])).toBe(values)
    expect(orderValuesByFieldOrder(empty, ['id'])).toBe(empty)
  })

  it('preserves __proto__ as an own data property', () => {
    const values = JSON.parse('{"extra":"value","__proto__":"submitted","first":"answer"}') as Record<string, string>

    const ordered = orderValuesByFieldOrder(values, ['__proto__', 'first'])

    expect(Object.keys(ordered)).toEqual(['__proto__', 'first', 'extra'])
    expect(Object.hasOwn(ordered, '__proto__')).toBe(true)
    expect(ordered['__proto__']).toBe('submitted')
    expect(Object.getPrototypeOf(ordered)).toBe(Object.prototype)
  })

  it('passes arrays, scalars, and null through unchanged', () => {
    const values = ['first', 'second']

    expect(orderValuesByFieldOrder(values, ['second', 'first'])).toBe(values)
    expect(orderValuesByFieldOrder('scalar', ['field'])).toBe('scalar')
    expect(orderValuesByFieldOrder(null, ['field'])).toBeNull()
  })
})
