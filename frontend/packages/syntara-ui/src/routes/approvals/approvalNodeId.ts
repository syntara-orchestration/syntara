/**
 * Helpers for matching approval records to canvas / activity IDs.
 *
 * `approval_node_id` is the canvas node ID. Loop identity is
 * `loop_iteration_path` (outermost first). Legacy / mock rows may still
 * encode iteration as `{nodeId}_iter_{n}` suffixes; those are a fallback only.
 * Activity records for later iterations use the composite key `{nodeId}#iter-{n}`.
 */

const LOOP_ITER_CHAIN = /(?:_iter_\d+)+$/
const COMPOSITE_ITER_SEP = '#iter-'

type ApprovalNodeRef = {
  approval_node_id: string
  status?: string
  loop_iteration_path?: number[]
}

/** Strip loop-iteration and composite-key suffixes to the canvas node ID. */
export function canvasNodeIdFromApprovalNodeId(id: string): string {
  const withoutLoopIter = id.replace(LOOP_ITER_CHAIN, '')
  const hashIdx = withoutLoopIter.indexOf(COMPOSITE_ITER_SEP)
  return hashIdx === -1 ? withoutLoopIter : withoutLoopIter.slice(0, hashIdx)
}

/** True when an approval record belongs to the given canvas or activity ID. */
export function matchesApprovalNodeId(approvalNodeId: string, canvasOrActivityId: string): boolean {
  return canvasNodeIdFromApprovalNodeId(approvalNodeId) === canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
}

function suffixIterationKey(approvalNodeId: string): number[] {
  const chain = LOOP_ITER_CHAIN.exec(approvalNodeId)?.[0] ?? ''
  const indices: number[] = []
  const iterNum = /_iter_(\d+)/g
  let match = iterNum.exec(chain)
  while (match !== null) {
    indices.push(Number(match[1]))
    match = iterNum.exec(chain)
  }
  return indices
}

function iterationSortKey(approval: ApprovalNodeRef): number[] {
  if (approval.loop_iteration_path && approval.loop_iteration_path.length > 0) {
    return approval.loop_iteration_path
  }
  return suffixIterationKey(approval.approval_node_id)
}

function compareIterationKeys(left: number[], right: number[]): number {
  const len = Math.max(left.length, right.length)
  for (let i = 0; i < len; i++) {
    const diff = (left[i] ?? -1) - (right[i] ?? -1)
    if (diff !== 0) return diff
  }
  return 0
}

function pickLatestLoopApproval<T extends ApprovalNodeRef>(matches: T[]): T | undefined {
  if (matches.length === 0) return undefined
  const pending = matches.filter((approval) => approval.status === 'pending')
  const pool = pending.length > 0 ? pending : matches
  const [latest, ...rest] = pool
  if (latest === undefined) return undefined
  return rest.reduce(
    (best, current) => (compareIterationKeys(iterationSortKey(current), iterationSortKey(best)) >= 0 ? current : best),
    latest
  )
}

export function findApprovalForCanvasNode<T extends ApprovalNodeRef>(
  approvals: T[],
  canvasOrActivityId: string
): T | undefined {
  const canvasId = canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
  if (canvasOrActivityId !== canvasId) {
    const exactSuffixed = approvals.find((approval) => approval.approval_node_id === canvasOrActivityId)
    if (exactSuffixed) return exactSuffixed
  }
  return pickLatestLoopApproval(
    approvals.filter((approval) => matchesApprovalNodeId(approval.approval_node_id, canvasOrActivityId))
  )
}

export function findApprovalIndexForCanvasNode<T extends ApprovalNodeRef>(
  approvals: T[],
  canvasOrActivityId: string
): number {
  const match = findApprovalForCanvasNode(approvals, canvasOrActivityId)
  return match === undefined ? -1 : approvals.indexOf(match)
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
