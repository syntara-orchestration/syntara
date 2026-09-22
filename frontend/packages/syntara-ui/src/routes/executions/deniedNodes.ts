/**
 * Helpers for the execution-level `denied_nodes` list and the per-node
 * `node_execute_denied` error payload.
 *
 * `ExecutionRead.denied_nodes` is typed as an untyped object array in the
 * generated contract, so entries are narrowed here instead of being cast.
 */

/** Stable error code the engine records on a node it was not allowed to run. */
export const NODE_EXECUTE_DENIED_CODE = 'node_execute_denied'

/** One entry of `execution.denied_nodes`. */
export type DeniedNode = {
  /** ID of the node in the workflow definition. */
  nodeId: string
  /** Node kind that was denied (e.g. `http_request`). */
  kind?: string
  /** Name of the policy that produced the deny. */
  deniedBy?: string
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined
}

function toDeniedNode(value: unknown): DeniedNode | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const nodeId = optionalString(record.node_id)
  if (!nodeId) return null
  return {
    nodeId,
    kind: optionalString(record.kind),
    deniedBy: optionalString(record.denied_by),
  }
}

/** Narrows `execution.denied_nodes` into well-formed entries, dropping anything unusable. */
export function parseDeniedNodes(value: unknown): DeniedNode[] {
  if (!Array.isArray(value)) return []
  return value.map(toDeniedNode).filter((entry): entry is DeniedNode => entry !== null)
}

/**
 * Turns a node's `error_details` into a readable sentence when it carries the
 * `node_execute_denied` payload. Returns `null` for any other error so callers
 * can fall back to showing the raw details.
 */
export function formatNodeDeniedError(errorDetails: string | null | undefined): string | null {
  if (!errorDetails?.includes(NODE_EXECUTE_DENIED_CODE)) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(errorDetails)
  } catch {
    return 'This step was not allowed to run for this execution.'
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
  const record = parsed as Record<string, unknown>
  if (record.code !== NODE_EXECUTE_DENIED_CODE) return null

  const deniedBy = optionalString(record.denied_by)
  return deniedBy
    ? `This step was not allowed to run for this execution. Denied by policy "${deniedBy}".`
    : 'This step was not allowed to run for this execution.'
}
