import { describe, expect, it } from 'vitest'

import {
  DENY_REQUIRES_NODE_ACTIONS_MESSAGE,
  isDeniableNodeAction,
  isDenyEffectAllowed,
  policyConditionsSchema,
  policyStatementSchema,
  STATEMENTS_JSON_INVALID_MESSAGE,
  validateStatementsJson,
} from './addProjectPolicySchema'

describe('isDeniableNodeAction', () => {
  it.each(['workflow_node:write', 'workflow_node:execute', 'workflow_node:*'])('accepts %s', (action) => {
    expect(isDeniableNodeAction(action)).toBe(true)
  })

  it.each(['workflow:write', 'workflow_node:read', 'workflow_node', '*', 'workflow_node:write:extra'])(
    'rejects %s',
    (action) => {
      expect(isDeniableNodeAction(action)).toBe(false)
    }
  )
})

describe('isDenyEffectAllowed', () => {
  it('leaves allow statements alone', () => {
    expect(isDenyEffectAllowed({ effect: 'allow', actions: ['workflow:delete'] })).toBe(true)
  })

  it('accepts a deny whose every action is a node action', () => {
    expect(isDenyEffectAllowed({ effect: 'deny', actions: ['workflow_node:write', 'workflow_node:execute'] })).toBe(
      true
    )
  })

  it('rejects a deny that mixes in a non-node action', () => {
    expect(isDenyEffectAllowed({ effect: 'deny', actions: ['workflow_node:write', 'workflow:delete'] })).toBe(false)
  })

  it('rejects a deny with no actions', () => {
    expect(isDenyEffectAllowed({ effect: 'deny', actions: [] })).toBe(false)
  })
})

describe('policyConditionsSchema', () => {
  it('accepts resource_labels as a string map', () => {
    const result = policyConditionsSchema.safeParse({ resource_labels: { kind: 'script' } })

    expect(result.success).toBe(true)
  })

  it('rejects a non-string resource label value', () => {
    expect(policyConditionsSchema.safeParse({ resource_labels: { kind: 7 } }).success).toBe(false)
  })

  it('passes through unrelated condition keys', () => {
    const result = policyConditionsSchema.safeParse({ resource_labels: { kind: 'script' }, tag: ['a'] })

    expect(result.success).toBe(true)
    expect(result.data).toMatchObject({ tag: ['a'] })
  })
})

describe('policyStatementSchema with node-kind conditions', () => {
  it('accepts a node-kind deny statement', () => {
    const statement = {
      effect: 'deny',
      actions: ['workflow_node:write'],
      scope: 'any',
      conditions: { resource_labels: { kind: 'script' } },
    }

    expect(policyStatementSchema.safeParse(statement).success).toBe(true)
  })

  it('reports the deny rule on the effect field', () => {
    const result = policyStatementSchema.safeParse({ effect: 'deny', actions: ['workflow:delete'], scope: 'any' })

    expect(result.success).toBe(false)
    expect(result.error?.issues[0]).toMatchObject({
      message: DENY_REQUIRES_NODE_ACTIONS_MESSAGE,
      path: ['effect'],
    })
  })
})

describe('validateStatementsJson', () => {
  it('accepts a valid statements array', () => {
    expect(validateStatementsJson('[{"effect":"allow","actions":["read"],"scope":"any"}]')).toBeNull()
  })

  it('reports the deny rule with its own message', () => {
    const json = JSON.stringify([{ effect: 'deny', actions: ['workflow:delete'], scope: 'any' }])

    expect(validateStatementsJson(json)).toBe(DENY_REQUIRES_NODE_ACTIONS_MESSAGE)
  })

  it('reports malformed JSON with the generic message', () => {
    expect(validateStatementsJson('not json')).toBe(STATEMENTS_JSON_INVALID_MESSAGE)
    expect(validateStatementsJson('{}')).toBe(STATEMENTS_JSON_INVALID_MESSAGE)
  })

  it('reports a structurally invalid statement with the generic message', () => {
    expect(validateStatementsJson('[{"effect":"allow"}]')).toBe(STATEMENTS_JSON_INVALID_MESSAGE)
  })
})
