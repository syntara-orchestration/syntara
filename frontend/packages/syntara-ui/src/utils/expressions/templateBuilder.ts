/**
 * Template expression builders for drag-and-drop field references.
 *
 * These produce the `${node_id.field.path}` format consumed by the backend
 * expression resolver.  Unlike the condition-expression serializer, these
 * build simple variable-reference expressions (no operators or groups).
 */

/** Safe characters for node IDs: alphanumeric, underscores, hyphens (matches generateActivityId format) */
const SAFE_NODE_ID = /^[a-zA-Z0-9_-]+$/

/** Execution activity records for later loop iterations use `{nodeId}#iter-{n}`. */
const COMPOSITE_ITER_SEP = '#iter-'

/** Safe characters for field path segments: alphanumeric, underscores, hyphens, spaces, brackets for array indexing (no dots — dots are path delimiters) */
const SAFE_FIELD_SEGMENT = /^[a-zA-Z0-9_ \-[\]]+$/

/**
 * Template expressions always reference the canvas node ID.
 * Strip execution composite keys (`{nodeId}#iter-{n}`) before interpolating.
 */
export function canvasNodeIdForExpression(nodeId: string): string {
  const hashIdx = nodeId.indexOf(COMPOSITE_ITER_SEP)
  return hashIdx === -1 ? nodeId : nodeId.slice(0, hashIdx)
}

function validateNodeId(nodeId: string): string {
  const canvasId = canvasNodeIdForExpression(nodeId)
  if (!SAFE_NODE_ID.test(canvasId)) {
    throw new Error('Invalid node ID: contains disallowed characters')
  }
  return canvasId
}

function validateFieldSegment(segment: string): string {
  if (!SAFE_FIELD_SEGMENT.test(segment)) {
    throw new Error('Invalid expression path segment: contains disallowed characters')
  }
  return segment
}

export type DragPayload = {
  /** The node's ID (e.g., "step_1_gather_info"), NOT the display name */
  nodeId: string
  fieldPath: string[]
}

export function buildExpression(payload: DragPayload): string {
  const safeNodeId = validateNodeId(payload.nodeId)
  const safePath = payload.fieldPath.map(validateFieldSegment)
  const path = [safeNodeId, ...safePath].join('.')
  return `\${${path}}`
}

export function buildContextExpression(contextPath: string): string {
  const pathToValidate = contextPath.startsWith('$') ? contextPath.slice(1) : contextPath
  for (const segment of pathToValidate.split('.')) {
    validateFieldSegment(segment)
  }
  return `\${${contextPath}}`
}
