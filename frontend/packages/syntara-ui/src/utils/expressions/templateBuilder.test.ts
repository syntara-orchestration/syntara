import { describe, expect, it } from 'vitest'

import { buildExpression, canvasNodeIdForExpression } from './templateBuilder'

describe('buildExpression', () => {
  it('builds simple field reference', () => {
    const result = buildExpression({
      nodeId: 'step_1_fetch',
      fieldPath: ['status'],
    })
    expect(result).toBe('${step_1_fetch.status}')
  })

  it('builds nested field reference', () => {
    const result = buildExpression({
      nodeId: 'step_2_process',
      fieldPath: ['data', 'result'],
    })
    expect(result).toBe('${step_2_process.data.result}')
  })

  it('builds array subscript reference with positive index', () => {
    const result = buildExpression({
      nodeId: 'step_3_list',
      fieldPath: ['items[0]'],
    })
    expect(result).toBe('${step_3_list.items[0]}')
  })

  it('builds array subscript reference with negative index', () => {
    const result = buildExpression({
      nodeId: 'step_4_array',
      fieldPath: ['results[-1]'],
    })
    expect(result).toBe('${step_4_array.results[-1]}')
  })

  it('builds nested array reference', () => {
    const result = buildExpression({
      nodeId: 'step_5_data',
      fieldPath: ['items[0]', 'name'],
    })
    expect(result).toBe('${step_5_data.items[0].name}')
  })

  it('strips execution composite iteration keys to the canvas node ID', () => {
    const result = buildExpression({
      nodeId: 'approval2#iter-5',
      fieldPath: ['status'],
    })
    expect(result).toBe('${approval2.status}')
  })

  it('throws error for invalid node ID with special characters', () => {
    expect(() =>
      buildExpression({
        nodeId: 'step.with.dots',
        fieldPath: ['field'],
      })
    ).toThrow('Invalid node ID: contains disallowed characters')
  })

  it('throws error for field path with dots', () => {
    expect(() =>
      buildExpression({
        nodeId: 'step_1',
        fieldPath: ['field.with.dots'],
      })
    ).toThrow('Invalid expression path segment: contains disallowed characters')
  })

  it('allows field names with spaces', () => {
    const result = buildExpression({
      nodeId: 'step_1',
      fieldPath: ['field name'],
    })
    expect(result).toBe('${step_1.field name}')
  })

  it('allows field names with hyphens', () => {
    const result = buildExpression({
      nodeId: 'step_1',
      fieldPath: ['field-name'],
    })
    expect(result).toBe('${step_1.field-name}')
  })

  it('allows field names with underscores', () => {
    const result = buildExpression({
      nodeId: 'step_1',
      fieldPath: ['field_name'],
    })
    expect(result).toBe('${step_1.field_name}')
  })
})

describe('canvasNodeIdForExpression', () => {
  it('returns canvas IDs unchanged', () => {
    expect(canvasNodeIdForExpression('approval2')).toBe('approval2')
  })

  it('strips a composite iteration suffix', () => {
    expect(canvasNodeIdForExpression('approval2#iter-5')).toBe('approval2')
  })
})
