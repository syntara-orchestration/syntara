/**
 * Helpers for matching approval_node_id to canvas / activity IDs.
 *
 * Outside a loop, approval_node_id is the canvas node ID. Inside a loop body
 * each iteration stores ``{nodeId}_iter_{n}`` so the Approvals API unique
 * constraint is not violated (AAP-87702). Activity records for later
 * iterations use the composite key ``{nodeId}#iter-{n}``.
 */

const LOOP_ITER_SUFFIX = /_iter_\d+$/
const COMPOSITE_ITER_SEP = '#iter-'

/** Strip loop-iteration and composite-key suffixes to the canvas node ID. */
export function canvasNodeIdFromApprovalNodeId(id: string): string {
  const withoutLoopIter = id.replace(LOOP_ITER_SUFFIX, '')
  const hashIdx = withoutLoopIter.indexOf(COMPOSITE_ITER_SEP)
  return hashIdx === -1 ? withoutLoopIter : withoutLoopIter.slice(0, hashIdx)
}

/** True when an approval record belongs to the given canvas or activity ID. */
export function matchesApprovalNodeId(approvalNodeId: string, canvasOrActivityId: string): boolean {
  return canvasNodeIdFromApprovalNodeId(approvalNodeId) === canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
}

export function findApprovalForCanvasNode<T extends { approval_node_id: string }>(
  approvals: T[],
  canvasOrActivityId: string
): T | undefined {
  return approvals.find((a) => matchesApprovalNodeId(a.approval_node_id, canvasOrActivityId))
}

export function findApprovalIndexForCanvasNode<T extends { approval_node_id: string }>(
  approvals: T[],
  canvasOrActivityId: string
): number {
  return approvals.findIndex((a) => matchesApprovalNodeId(a.approval_node_id, canvasOrActivityId))
}

export function findNodeByApprovalNodeId<T extends { id?: unknown }>(
  nodes: T[],
  approvalNodeId: string
): T | undefined {
  const canvasId = canvasNodeIdFromApprovalNodeId(approvalNodeId)
  return nodes.find((n) => n.id === canvasId || n.id === approvalNodeId)
}

export function lookupMapByApprovalNodeId<T>(
  map: ReadonlyMap<string, T> | undefined,
  approvalNodeId: string | null | undefined
): T | undefined {
  if (!map || !approvalNodeId) return undefined
  const canvasId = canvasNodeIdFromApprovalNodeId(approvalNodeId)
  return map.get(canvasId) ?? map.get(approvalNodeId)
}
