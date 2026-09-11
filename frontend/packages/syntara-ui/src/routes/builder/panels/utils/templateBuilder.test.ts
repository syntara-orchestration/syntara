import { describe, expect, it } from 'vitest'

import { buildContextExpression, buildExpression } from '../../../../utils/expressions/templateBuilder'

describe('buildExpression', () => {
  it('builds expression with node ID and single field', () => {
    const result = buildExpression({
      nodeId: 'step_1_gather_info',
      fieldPath: ['hostname'],
    })

    expect(result).toBe('${step_1_gather_info.hostname}')
  })

  it('builds expression with nested field path', () => {
    const result = buildExpression({
      nodeId: 'step_1_gather_info',
      fieldPath: ['stdout_json', 'hostname'],
    })

    expect(result).toBe('${step_1_gather_info.stdout_json.hostname}')
  })

  it('handles deeply nested paths', () => {
    const result = buildExpression({
      nodeId: 'fetch_order',
      fieldPath: ['data', 'items', 'name'],
    })

    expect(result).toBe('${fetch_order.data.items.name}')
  })

  it('handles single path segment', () => {
    const result = buildExpression({
      nodeId: 'trigger_manual',
      fieldPath: ['stdout'],
    })

    expect(result).toBe('${trigger_manual.stdout}')
  })

  it('strips execution composite iteration keys to the canvas node ID', () => {
    const result = buildExpression({
      nodeId: 'approval2#iter-5',
      fieldPath: ['hostname'],
    })
    expect(result).toBe('${approval2.hostname}')
  })

  it('rejects nodeId containing expression injection characters', () => {
    expect(() => buildExpression({ nodeId: 'node}; malicious; ${', fieldPath: ['field'] })).toThrow(
      'disallowed characters'
    )
  })

  it('rejects fieldPath containing closing brace', () => {
    expect(() => buildExpression({ nodeId: 'valid_node', fieldPath: ['field}'] })).toThrow('disallowed characters')
  })

  it('accepts node IDs with hyphens', () => {
    const result = buildExpression({
      nodeId: 'my-node-1',
      fieldPath: ['hostname'],
    })

    expect(result).toBe('${my-node-1.hostname}')
  })

  it('accepts field path segments with spaces', () => {
    const result = buildExpression({
      nodeId: 'step_1',
      fieldPath: ['field name'],
    })

    expect(result).toBe('${step_1.field name}')
  })

  it('rejects nodeId containing dots to prevent ambiguous paths', () => {
    expect(() => buildExpression({ nodeId: 'a.b', fieldPath: ['c'] })).toThrow('Invalid node ID')
  })

  it('rejects nodeId containing spaces', () => {
    expect(() => buildExpression({ nodeId: 'my node', fieldPath: ['field'] })).toThrow('Invalid node ID')
  })

  it('rejects field path segments containing dots', () => {
    expect(() => buildExpression({ nodeId: 'step_1', fieldPath: ['stdout.json'] })).toThrow('disallowed characters')
  })
})

describe('buildContextExpression', () => {
  it('builds expression for $now', () => {
    expect(buildContextExpression('$now')).toBe('${$now}')
  })

  it('builds expression for $today', () => {
    expect(buildContextExpression('$today')).toBe('${$today}')
  })

  it('builds expression for $vars.myVariable', () => {
    expect(buildContextExpression('$vars.myVariable')).toBe('${$vars.myVariable}')
  })

  it('builds expression for $execution.id', () => {
    expect(buildContextExpression('$execution.id')).toBe('${$execution.id}')
  })

  it('accepts context path without $ prefix (workflow_context namespace)', () => {
    expect(buildContextExpression('workflow_context.workflow.name')).toBe('${workflow_context.workflow.name}')
  })

  it('rejects context path with injection attempt', () => {
    expect(() => buildContextExpression('$now}; evil')).toThrow('disallowed characters')
  })
})

describe('buildExpression edge cases', () => {
  it('produces node-only expression with empty fieldPath', () => {
    const result = buildExpression({ nodeId: 'step_1', fieldPath: [] })
    expect(result).toBe('${step_1}')
  })
})
