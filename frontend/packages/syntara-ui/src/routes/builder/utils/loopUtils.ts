import { EdgeHandleEnum } from '@syntara/contracts'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { filterRealEdges, filterRealNodes } from './filterHelpers'
import type { EdgeType } from './workflowToGraph'

type GetLoopBodyMapOptions = {
  /** When true, also includes direct targets of the loop's done handle (for group drag). */
  includeDoneBranch?: boolean
}

/**
 * Traverses edges from each Loop node's loop handle to identify all body nodes via BFS.
 * Expects pre-filtered real nodes and edges (no placeholder nodes, no button edges).
 * Returns a map from loop node ID to the ordered array of its body node IDs.
 */
export function getLoopBodyMap(
  realNodes: NodeType[],
  realEdges: EdgeType[],
  { includeDoneBranch = false }: GetLoopBodyMapOptions = {}
): Map<string, string[]> {
  const loopBodies = new Map<string, string[]>()

  realNodes.forEach((node) => {
    if (node.type !== FlowNodeType.LOOP) return

    const bodyNodeIds: string[] = []
    const seen = new Set<string>()

    const addBodyNode = (nodeId: string) => {
      if (seen.has(nodeId)) return
      seen.add(nodeId)
      bodyNodeIds.push(nodeId)
    }

    const loopEdges = realEdges.filter((e) => e.source === node.id && e.sourceHandle === EdgeHandleEnum.LOOP)

    loopEdges.forEach((loopEdge) => {
      const visited = new Set<string>()
      const queue: string[] = [loopEdge.target]
      // SECURITY: Secondary iteration limit as defense-in-depth (visited set is primary defense)
      const MAX_ITERATIONS = 10_000
      let iterations = 0

      while (queue.length > 0 && iterations < MAX_ITERATIONS) {
        iterations++
        const nodeId = queue.shift()!
        if (visited.has(nodeId)) continue
        visited.add(nodeId)

        addBodyNode(nodeId)

        // SECURITY: Domain-invariant check — loop body can't exceed total node count
        if (bodyNodeIds.length > realNodes.length) break

        // Follow source edges, but not edges back to the loop node (prevents circular traversal)
        const outgoing = realEdges.filter(
          (e) => e.source === nodeId && e.sourceHandle === EdgeHandleEnum.SOURCE && e.target !== node.id
        )
        outgoing.forEach((e) => {
          if (!visited.has(e.target)) queue.push(e.target)
        })
      }
    })

    if (includeDoneBranch) {
      const doneEdges = realEdges.filter(
        (e) =>
          e.source === node.id &&
          e.sourceHandle === EdgeHandleEnum.DONE &&
          e.targetHandle !== EdgeHandleEnum.END
      )
      doneEdges.forEach((e) => addBodyNode(e.target))
    }

    if (bodyNodeIds.length > 0) {
      loopBodies.set(node.id, bodyNodeIds)
    }
  })

  return loopBodies
}

/**
 * Returns every node ID that belongs to a loop group (loop header + body + done branch).
 */
export function getLoopGroupNodeIds(nodes: NodeType[], edges: EdgeType[]): Set<string> {
  const bodyMap = getLoopBodyMap(filterRealNodes(nodes), filterRealEdges(edges), { includeDoneBranch: true })
  const ids = new Set<string>()
  bodyMap.forEach((bodyIds, loopId) => {
    ids.add(loopId)
    bodyIds.forEach((id) => ids.add(id))
  })
  return ids
}

/**
 * Collects canvas positions for every node in each loop group so they persist together on save.
 */
export function collectLoopGroupPositions(
  nodes: NodeType[],
  edges: EdgeType[],
  toKey: (nodeId: string) => string
): Record<string, { x: number; y: number }> {
  const bodyMap = getLoopBodyMap(filterRealNodes(nodes), filterRealEdges(edges), { includeDoneBranch: true })
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const positions: Record<string, { x: number; y: number }> = {}

  bodyMap.forEach((bodyIds, loopId) => {
    const loopNode = nodeById.get(loopId)
    if (loopNode) positions[toKey(loopId)] = loopNode.position
    for (const bodyId of bodyIds) {
      const bodyNode = nodeById.get(bodyId)
      if (bodyNode) positions[toKey(bodyId)] = bodyNode.position
    }
  })

  return positions
}
