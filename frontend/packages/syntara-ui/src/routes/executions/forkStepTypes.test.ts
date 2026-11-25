import { describe, expect, it } from 'vitest'

import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { blockedForkStepTypes, forkLosesAllTriggers, withoutForkStepTypes } from './forkStepTypes'

function verdict(kind: string, canWrite: boolean, label?: string): NodeKind {
  return { kind, category: 'action', can_write: canWrite, blocked_by: canWrite ? null : { kind, label: label ?? kind } }
}

const VERDICTS = new Map<string, NodeKind>([
  ['script', verdict('script', false, 'Script')],
  ['webhook', verdict('webhook', false, 'Webhook')],
  ['http', verdict('http', true)],
  ['manual', verdict('manual', true)],
])

const DEFINITION: Record<string, unknown> = {
  schema_version: '2.0.0',
  name: 'Run',
  nodes: [
    { id: 'a', type: 'http', position: { x: 0, y: 0 } },
    { id: 'b', type: 'script', position: { x: 1, y: 1 } },
    { id: 'c', type: 'http' },
    { id: 'd', type: 'script' },
  ],
  edges: [
    { from: 't1', to: 'a' },
    { from: 'a', to: 'b' },
    { from: 'b', to: 'c', from_port: 'success' },
    { from: 'a', to: 'c' },
  ],
  triggers: [{ id: 't1', type: 'webhook' }],
}

describe('blockedForkStepTypes', () => {
  it('lists each blocked step type once with its label, nodes before triggers', () => {
    expect(blockedForkStepTypes(DEFINITION, VERDICTS)).toEqual([
      { kind: 'script', label: 'Script' },
      { kind: 'webhook', label: 'Webhook' },
    ])
  })

  it('allows step types without a verdict and tolerates a definition without steps', () => {
    expect(blockedForkStepTypes({ nodes: [{ id: 'x', type: 'unknown' }] }, VERDICTS)).toEqual([])
    expect(blockedForkStepTypes({}, VERDICTS)).toEqual([])
  })
})

describe('forkLosesAllTriggers', () => {
  it('is true only when there are triggers and all are removed', () => {
    expect(forkLosesAllTriggers(DEFINITION, ['webhook'])).toBe(true)
    expect(forkLosesAllTriggers(DEFINITION, ['script'])).toBe(false)
    expect(forkLosesAllTriggers({ ...DEFINITION, triggers: [] }, ['webhook'])).toBe(false)
    expect(forkLosesAllTriggers({ triggers: [{ id: 't1', type: 'webhook' }, { type: 'manual' }] }, ['webhook'])).toBe(
      false
    )
  })
})

describe('withoutForkStepTypes', () => {
  it('removes the nodes and triggers of the kinds and every edge touching them', () => {
    const result = withoutForkStepTypes(DEFINITION, ['script', 'webhook'])

    expect(result).toEqual({
      schema_version: '2.0.0',
      name: 'Run',
      nodes: [
        { id: 'a', type: 'http', position: { x: 0, y: 0 } },
        { id: 'c', type: 'http' },
      ],
      edges: [{ from: 'a', to: 'c' }],
      triggers: [],
    })
  })

  it('does not mutate the input', () => {
    const before = structuredClone(DEFINITION)
    withoutForkStepTypes(DEFINITION, ['script'])
    expect(DEFINITION).toEqual(before)
  })

  it('leaves absent arrays absent', () => {
    expect(withoutForkStepTypes({ name: 'x', nodes: [{ id: 'b', type: 'script' }] }, ['script'])).toEqual({
      name: 'x',
      nodes: [],
    })
  })
})
