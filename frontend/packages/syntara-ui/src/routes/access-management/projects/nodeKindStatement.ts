import type { NodeKind } from '../../../hooks/useNodeKindsQuery'

import { NODE_KIND_LABEL, NODE_RESOURCE_TYPE, validateStatementsJson } from './addProjectPolicySchema'

/** Effect a node-kind statement may carry. */
export type NodeKindStatementEffect = 'allow' | 'deny'

/** Action selection offered by the node-kind statement helper. */
export type NodeKindStatementAction = 'write' | 'execute' | 'both'

/** Actions each helper selection expands to. */
const ACTIONS_BY_SELECTION: Record<NodeKindStatementAction, readonly string[]> = {
  write: ['write'],
  execute: ['execute'],
  both: ['write', 'execute'],
}

export type NodeKindStatement = {
  effect: NodeKindStatementEffect
  actions: string[]
  scope: 'project'
  conditions: { resource_labels: Record<string, string> }
}

/**
 * Build a well-formed `workflow_node` statement for one node kind.
 *
 * The kind is carried as the `kind` resource label, which is how the
 * authorization layer targets a node kind. The statement is written at
 * `project` scope because the helper only feeds project policies, and the
 * API rejects any other scope there.
 */
export function buildNodeKindStatement(options: {
  effect: NodeKindStatementEffect
  action: NodeKindStatementAction
  kind: string
}): NodeKindStatement {
  return {
    effect: options.effect,
    actions: ACTIONS_BY_SELECTION[options.action].map((action) => `${NODE_RESOURCE_TYPE}:${action}`),
    scope: 'project',
    conditions: { resource_labels: { [NODE_KIND_LABEL]: options.kind } },
  }
}

/**
 * Append a statement to the raw statements JSON, keeping the editor's formatting.
 *
 * @param statementsJson Current textarea contents.
 * @param statement Statement to append.
 * @returns The new JSON text, or an error message when the current text is not a
 *   JSON array of valid statements (appending would silently discard it).
 */
export function appendNodeKindStatement(
  statementsJson: string,
  statement: NodeKindStatement
): { json: string; error?: undefined } | { json?: undefined; error: string } {
  const trimmed = statementsJson.trim()
  if (trimmed === '') return { json: JSON.stringify([statement], null, 2) }

  const message = validateStatementsJson(trimmed)
  if (message) return { error: `Fix the statements JSON before adding a statement: ${message}` }

  const parsed = JSON.parse(trimmed) as unknown[]
  return { json: JSON.stringify([...parsed, statement], null, 2) }
}

/**
 * Node kinds that may carry the chosen effect and action.
 *
 * A deny is only accepted for kinds whose `deniable_actions` cover every action
 * in the selection — flow control kinds can never be denied, and triggers only
 * for `write`. An allow applies to every kind.
 */
export function selectableNodeKinds(
  nodeKinds: readonly NodeKind[],
  effect: NodeKindStatementEffect,
  action: NodeKindStatementAction
): NodeKind[] {
  if (effect === 'allow') return [...nodeKinds]

  const required = ACTIONS_BY_SELECTION[action]
  return nodeKinds.filter((nodeKind) =>
    required.every((needed) => nodeKind.deniable_actions.includes(needed) || nodeKind.deniable_actions.includes('*'))
  )
}
