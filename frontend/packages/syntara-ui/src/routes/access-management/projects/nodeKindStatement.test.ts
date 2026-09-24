import { describe, expect, it } from 'vitest'

import type { NodeKind } from '../../../hooks/useNodeKindsQuery'

import { appendNodeKindStatement, buildNodeKindStatement, selectableNodeKinds } from './nodeKindStatement'

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    enabled: true,
    switchable: true,
    deniable_actions: ['write', 'execute'],
    can_write: true,
    attributes: [],
    ...overrides,
  }
}

const registry: NodeKind[] = [
  kind({ kind: 'script' }),
  kind({ kind: 'manual_trigger', category: 'trigger', deniable_actions: ['write'] }),
  kind({ kind: 'condition', category: 'flow_control', switchable: false, deniable_actions: [] }),
]

describe('buildNodeKindStatement', () => {
  it('targets the node kind through the kind resource label', () => {
    expect(buildNodeKindStatement({ effect: 'deny', action: 'write', kind: 'script' })).toEqual({
      effect: 'deny',
      actions: ['workflow_node:write'],
      scope: 'project',
      conditions: { resource_labels: { kind: 'script' } },
    })
  })

  it('normalizes non-empty attribute labels and drops empty values', () => {
    expect(
      buildNodeKindStatement({
        effect: 'deny',
        action: 'write',
        kind: 'script',
        attributes: { language: ' Python ', integration_id: '   ' },
      }).conditions.resource_labels
    ).toEqual({ kind: 'script', language: 'python' })
  })

  it('expands the both selection into two actions', () => {
    expect(buildNodeKindStatement({ effect: 'deny', action: 'both', kind: 'agentic' }).actions).toEqual([
      'workflow_node:write',
      'workflow_node:execute',
    ])
  })

  it('builds an allow statement the same way', () => {
    expect(buildNodeKindStatement({ effect: 'allow', action: 'execute', kind: 'script' })).toMatchObject({
      effect: 'allow',
      actions: ['workflow_node:execute'],
    })
  })
})

describe('appendNodeKindStatement', () => {
  const statement = buildNodeKindStatement({ effect: 'deny', action: 'write', kind: 'script' })

  it('creates the array when the editor is empty', () => {
    const result = appendNodeKindStatement('   ', statement)

    expect(JSON.parse(result.json ?? '')).toEqual([statement])
  })

  it('appends to an existing array and keeps the earlier statements', () => {
    const existing = JSON.stringify([{ effect: 'allow', actions: ['read'], scope: 'any' }])

    const result = appendNodeKindStatement(existing, statement)

    expect(JSON.parse(result.json ?? '')).toEqual([{ effect: 'allow', actions: ['read'], scope: 'any' }, statement])
  })

  it('pretty-prints with two-space indentation', () => {
    const result = appendNodeKindStatement('', statement)

    expect(result.json).toContain('\n  {')
  })

  it('refuses to append to invalid JSON so nothing is discarded', () => {
    const result = appendNodeKindStatement('not json', statement)

    expect(result.json).toBeUndefined()
    expect(result.error).toContain('Fix the statements JSON')
  })

  it('refuses to append when an existing statement breaks the deny rule', () => {
    const existing = JSON.stringify([{ effect: 'deny', actions: ['workflow:delete'], scope: 'any' }])

    expect(appendNodeKindStatement(existing, statement).error).toContain('deny statement')
  })
})

describe('selectableNodeKinds', () => {
  it('offers every kind for an allow statement', () => {
    expect(selectableNodeKinds(registry, 'allow', 'both').map((entry) => entry.kind)).toEqual([
      'script',
      'manual_trigger',
      'condition',
    ])
  })

  it('never offers a flow control kind for a deny', () => {
    expect(selectableNodeKinds(registry, 'deny', 'write').map((entry) => entry.kind)).toEqual([
      'script',
      'manual_trigger',
    ])
  })

  it('drops triggers when execute is part of the deny', () => {
    expect(selectableNodeKinds(registry, 'deny', 'execute').map((entry) => entry.kind)).toEqual(['script'])
    expect(selectableNodeKinds(registry, 'deny', 'both').map((entry) => entry.kind)).toEqual(['script'])
  })

  it('accepts a wildcard deniable action', () => {
    const wildcard = [kind({ kind: 'mcp_tool', deniable_actions: ['*'] })]

    expect(selectableNodeKinds(wildcard, 'deny', 'both')).toHaveLength(1)
  })
})
