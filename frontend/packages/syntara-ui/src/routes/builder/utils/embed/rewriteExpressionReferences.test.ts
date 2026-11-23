import { describe, expect, it } from 'vitest'

import { rewriteExpressionReferences } from './rewriteExpressionReferences'

const idMap = new Map([
  ['task_a', 'activity_new_a'],
  ['task_b', 'activity_new_b'],
])
const sourceNodeIds = new Set(['task_a', 'task_b', 'trigger_excluded'])

describe('rewriteExpressionReferences', () => {
  it('rewrites a reference to a copied node id, preserving the field path', () => {
    const { value } = rewriteExpressionReferences('${task_a.outputs.order_id}', idMap, sourceNodeIds)
    expect(value).toBe('${activity_new_a.outputs.order_id}')
  })

  it('rewrites references nested inside objects and arrays without mutating the input', () => {
    const input = { a: ['${task_a.x}', { b: '${task_b.y[0]}' }], c: 'static' }
    const snapshot = JSON.parse(JSON.stringify(input)) as typeof input
    const { value } = rewriteExpressionReferences(input, idMap, sourceNodeIds)
    expect(value).toEqual({ a: ['${activity_new_a.x}', { b: '${activity_new_b.y[0]}' }], c: 'static' })
    expect(input).toEqual(snapshot) // no mutation
  })

  it('leaves non-node namespaces (trigger/input/loop) untouched', () => {
    const { value, danglingRefs } = rewriteExpressionReferences('${trigger.url} ${input.name}', idMap, sourceNodeIds)
    expect(value).toBe('${trigger.url} ${input.name}')
    expect(danglingRefs).toHaveLength(0)
  })

  it('reports a reference to a source node that was not copied (excluded trigger) as dangling', () => {
    const { value, danglingRefs } = rewriteExpressionReferences('${trigger_excluded.field}', idMap, sourceNodeIds)
    expect(value).toBe('${trigger_excluded.field}') // left as-is
    expect(danglingRefs).toEqual([{ namespace: 'trigger_excluded', expression: '${trigger_excluded.field}' }])
  })

  it('does not corrupt a field path that merely contains an id-like substring', () => {
    // `task_a_total` is a different namespace than `task_a`; must not be rewritten.
    const { value } = rewriteExpressionReferences('${task_a_total.x}', idMap, sourceNodeIds)
    expect(value).toBe('${task_a_total.x}')
  })

  it('rewrites multiple references within one string', () => {
    const { value } = rewriteExpressionReferences('${task_a.x}-${task_b.y}', idMap, sourceNodeIds)
    expect(value).toBe('${activity_new_a.x}-${activity_new_b.y}')
  })
})
