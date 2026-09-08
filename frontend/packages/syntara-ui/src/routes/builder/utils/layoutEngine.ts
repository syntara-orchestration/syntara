import Dagre from '@dagrejs/dagre'
import { ActivityTypeEnum, EdgeHandleEnum } from '@syntara/contracts'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { filterRealEdges, filterRealNodes } from './filterHelpers'
import { LOOP_BODY_SPACING } from './layoutConstants'
import type { EdgeType } from './workflowToGraph'

type DagreNodeLabel = {
  x: number
  y: number
}

function isDagreNodeLabel(value: unknown): value is DagreNodeLabel {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.x === 'number' && typeof v.y === 'number'
}

/**
 * Type-safe wrapper around dagre's `graph.node()` which is typed as `any`.
 * After `Dagre.layout()`, every node label is guaranteed to carry x/y coords.
 */
function getNodeLabel(g: Dagre.graphlib.Graph, nodeId: string): DagreNodeLabel {
  const raw: unknown = g.node(nodeId)
  if (!isDagreNodeLabel(raw)) {
    throw new Error(`Missing Dagre coordinates for node "${nodeId}"`)
  }
  return raw
}

const markerEnd = { type: 'arrowclosed' as const }

type LayoutOptions = {
  direction: 'TB' | 'LR'
}

type LoopBodyPosition = {
  x: number
  y: number
}

type BodyNodeWithPosition = {
  nodeId: string
  width: number
  height: number
  dagreX: number
}

/**
 * Calculate loop body node positions relative to their parent loop node
 */
function calculateLoopBodyPositions(
  loopBodies: Map<string, string[]>,
  realNodes: NodeType[],
  g: Dagre.graphlib.Graph
): Map<string, LoopBodyPosition> {
  const loopBodyPositions = new Map<string, LoopBodyPosition>()

  loopBodies.forEach((bodyNodeIds, loopId) => {
    const loopNode = realNodes.find((n) => n.id === loopId)
    const loopPositionCenter = getNodeLabel(g, loopId) // Dagre returns CENTER coordinates
    const loopWidth = loopNode?.measured?.width ?? 0
    const loopHeight = loopNode?.measured?.height ?? 0

    // Convert dagre CENTER coordinates to React Flow TOP-LEFT coordinates
    const loopX = loopPositionCenter.x - loopWidth / 2
    const loopY = loopPositionCenter.y - loopHeight / 2

    // Get all body nodes with their Dagre positions (maintain dagre order)
    const bodyNodesWithPositions: BodyNodeWithPosition[] = bodyNodeIds
      .map((nodeId) => {
        const node = realNodes.find((n) => n.id === nodeId)
        const position = getNodeLabel(g, nodeId)
        return {
          nodeId,
          width: node?.measured?.width ?? 0,
          height: node?.measured?.height ?? 0,
          dagreX: position.x,
        }
      })
      .sort((a, b) => a.dagreX - b.dagreX)

    // Position nodes to the right of loop node AND below it to fit inside the loop boundary
    // Use unified spacing constants for consistency with manual positioning
    let currentX = loopX + loopWidth + LOOP_BODY_SPACING.horizontal
    const baseY = loopY + LOOP_BODY_SPACING.vertical

    // Assign positions to each body node (flowing left to right)
    bodyNodesWithPositions.forEach((bodyNode) => {
      loopBodyPositions.set(bodyNode.nodeId, {
        x: currentX,
        y: baseY,
      })
      currentX += bodyNode.width + LOOP_BODY_SPACING.nodeGap
    })
  })

  return loopBodyPositions
}

/**
 * Identify loop structures and their body nodes
 */
function identifyLoopStructures(realNodes: NodeType[], realEdges: EdgeType[]) {
  const loopBodyNodes = new Set<string>()
  const loopParents = new Map<string, string>() // Map: nodeId -> loopNodeId
  const loopBodies = new Map<string, string[]>() // Map: loopNodeId -> array of body node IDs

  realNodes.forEach((node) => {
    if (node.type === 'loop') {
      // Find all edges from this loop's 'loop' handle
      const loopEdges = realEdges.filter((e) => e.source === node.id && e.sourceHandle === EdgeHandleEnum.LOOP)
      const bodyNodeIds: string[] = []

      loopEdges.forEach((loopEdge) => {
        // Traverse from loop edge to find all nodes that connect back to loop's end handle
        const visited = new Set<string>()
        const queue: string[] = [loopEdge.target]

        // SECURITY: Secondary iteration limit as defense-in-depth (visited set is primary defense)
        const MAX_ITERATIONS = 10_000
        let iterations = 0

        while (queue.length > 0 && iterations < MAX_ITERATIONS) {
          iterations++
          const nodeId = queue[0]
          queue.shift()
          if (visited.has(nodeId)) continue
          visited.add(nodeId)

          loopBodyNodes.add(nodeId)
          loopParents.set(nodeId, node.id)
          bodyNodeIds.push(nodeId)

          // SECURITY: Domain-invariant check — loop body can't exceed total node count
          if (loopBodyNodes.size > realNodes.length) {
            break
          }

          // Find outgoing edges (but don't follow edges back to the loop node)
          // We exclude ANY edge that points back to the loop node to prevent circular traversal
          const outgoing = realEdges.filter(
            (e) => e.source === nodeId && e.sourceHandle === EdgeHandleEnum.SOURCE && e.target !== node.id // Don't follow edges back to the loop node itself
          )

          outgoing.forEach((e) => {
            if (!visited.has(e.target)) {
              queue.push(e.target)
            }
          })
        }
      })

      if (bodyNodeIds.length > 0) {
        loopBodies.set(node.id, bodyNodeIds)
      }
    }
  })

  return { loopBodyNodes, loopParents, loopBodies }
}

type BranchOrdering = {
  // Ordered list of branch targets (handles all branch types uniformly)
  ordered: Array<{ handle: string; target: string }>
}

/**
 * Compare switch case handles (case_0, case_1, ..., default)
 */
function compareSwitchHandles(a: string, b: string): number {
  const aIsCase = a.startsWith('case_')
  const bIsCase = b.startsWith('case_')
  if (aIsCase && bIsCase) {
    const aIndex = Number.parseInt(a.replace('case_', ''), 10)
    const bIndex = Number.parseInt(b.replace('case_', ''), 10)
    return aIndex - bIndex
  }
  if (aIsCase) return -1 // Cases before default
  if (bIsCase) return 1
  return 0
}

/**
 * Compare two-way branch handles by priority (first handle on top)
 */
function compareTwoWayHandles(a: string, b: string, topHandle: string): number {
  if (a === topHandle) return -1
  if (b === topHandle) return 1
  return 0
}

/**
 * Compare function for sorting branch handles by priority
 */
function compareBranchHandles(
  a: { handle: string; target: string },
  b: { handle: string; target: string },
  nodeType: NodeType['type']
): number {
  if (nodeType === ActivityTypeEnum.CONDITION) return compareTwoWayHandles(a.handle, b.handle, EdgeHandleEnum.TRUE)
  if (nodeType === ActivityTypeEnum.APPROVAL) return compareTwoWayHandles(a.handle, b.handle, EdgeHandleEnum.APPROVED)
  if (nodeType === ActivityTypeEnum.SWITCH) return compareSwitchHandles(a.handle, b.handle)
  if (nodeType === ActivityTypeEnum.LOOP) return compareTwoWayHandles(a.handle, b.handle, EdgeHandleEnum.DONE)
  return 0
}

/**
 * Build map of branch nodes and their desired target ordering
 * All branch types are treated uniformly as ordered lists:
 * - Condition: [true, false]
 * - Approval: [approved, rejected]
 * - Switch: [case_0, case_1, ..., default]
 * - Loop: [done, loop]
 */
function buildBranchNodeOrdering(edges: EdgeType[], realNodes: NodeType[]): Map<string, BranchOrdering> {
  const branchNodeOrdering = new Map<string, BranchOrdering>()

  // Identify branching node types
  const branchingNodes = new Set<string>()
  realNodes.forEach((node) => {
    if (
      node.type === ActivityTypeEnum.CONDITION ||
      node.type === ActivityTypeEnum.APPROVAL ||
      node.type === ActivityTypeEnum.SWITCH ||
      node.type === ActivityTypeEnum.LOOP
    ) {
      branchingNodes.add(node.id)
    }
  })

  // Collect all edges from branching nodes
  edges.forEach((edge) => {
    if (!branchingNodes.has(edge.source)) return

    const existing = branchNodeOrdering.get(edge.source) ?? { ordered: [] }
    existing.ordered.push({ handle: edge.sourceHandle ?? '', target: edge.target })
    branchNodeOrdering.set(edge.source, existing)
  })

  // Sort ordered branches by handle priority (type-specific)
  branchNodeOrdering.forEach((ordering, nodeId) => {
    const sourceNode = realNodes.find((n) => n.id === nodeId)
    if (!sourceNode) return

    ordering.ordered.sort((a, b) => compareBranchHandles(a, b, sourceNode.type))
  })

  return branchNodeOrdering
}

type BranchPositionContext = {
  nodeId: string
  baseY: number
  nodeHeight: number
  branchNodeOrdering: Map<string, BranchOrdering>
  g: Dagre.graphlib.Graph
}

/**
 * Correct Y position for branch target nodes by anchoring them to the source branch node.
 * Works for all branch types: condition, approval, switch, loop.
 * Always repositions targets with consistent spacing to prevent overlap.
 */
function correctBranchNodePosition(ctx: BranchPositionContext): number {
  const { nodeId, baseY, nodeHeight, branchNodeOrdering, g } = ctx
  // Check if this node is a branch target
  for (const [sourceNodeId, ordering] of branchNodeOrdering.entries()) {
    // Build a map of distinct targets with their first occurrence index
    // Multiple handles can point to the same target - we only position it once
    const distinctTargets = new Map<string, number>()
    ordering.ordered.forEach((o, index) => {
      if (!distinctTargets.has(o.target)) {
        distinctTargets.set(o.target, index)
      }
    })

    // Check if this node is in the distinct target set
    if (!distinctTargets.has(nodeId)) continue

    // Find which position this node should be at (0-based index in distinct list)
    const distinctTargetList = Array.from(distinctTargets.keys())
    const positionIndex = distinctTargetList.indexOf(nodeId)
    if (positionIndex === -1) continue

    // Always reposition branch targets anchored to the source node
    // This ensures proper spacing even when Dagre places nodes at the same Y
    // Targets are centered as a group around the source node's vertical center
    const sourceNodeY = getNodeLabel(g, sourceNodeId).y

    // Calculate the total height needed for all targets
    const targetCount = distinctTargetList.length
    const nodeGap = 20 // Gap between consecutive nodes

    // Total height = sum of all target heights + gaps between them
    // For simplicity, assume all targets have similar height (use current node's height as reference)
    const totalHeight = targetCount * nodeHeight + (targetCount - 1) * nodeGap

    // Start position: center the entire group around the source node's center
    const groupStartY = sourceNodeY - totalHeight / 2

    // Position this target within the group
    const newY = groupStartY + positionIndex * (nodeHeight + nodeGap)
    return newY
  }

  return baseY
}

/**
 * Applies Dagre layout algorithm to position nodes in a hierarchical flow
 * with special handling for loop structures
 */
export function getLayoutedElements(nodes: NodeType[], edges: EdgeType[], options: LayoutOptions) {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  // Dagre configuration tuned for branching nodes (switch, condition, approval, loop)
  // - ranksep: vertical spacing between ranks
  // - nodesep: horizontal spacing between nodes in the same rank (accounts for branch handles)
  // - ranker: 'network-simplex' produces fewer edge crossings than 'tight-tree'
  g.setGraph({ rankdir: options.direction, ranksep: 120, nodesep: 90, ranker: 'network-simplex' })

  const realNodes = filterRealNodes(nodes)
  const realEdges = filterRealEdges(edges)

  // Identify loop structures - find nodes in loop bodies
  const { loopBodyNodes, loopBodies } = identifyLoopStructures(realNodes, realEdges)

  // For layout purposes, exclude loop-back edges (edges to loop's end handle)
  // This prevents Dagre from trying to create a circular layout
  const layoutEdges = realEdges.filter((edge) => edge.targetHandle !== 'end')

  // Add edges to Dagre with weights to control visual ordering
  // Higher weights encourage Dagre to position targets vertically closer to handle order
  layoutEdges.forEach((edge) => {
    const edgeConfig: { weight?: number } = {}

    // Assign weights to control branch ordering:
    // - Condition nodes: 'true' (2) appears above 'false' (1)
    // - Approval nodes: 'approved' (2) appears above 'rejected' (1)
    // - Loop nodes: 'done' (2) appears above 'loop' (1)
    // - Switch nodes: descending weights preserve case order (case_0=10, case_1=9, ..., default=1)
    if (edge.sourceHandle === EdgeHandleEnum.TRUE || edge.sourceHandle === EdgeHandleEnum.APPROVED) {
      edgeConfig.weight = 2
    } else if (edge.sourceHandle === EdgeHandleEnum.FALSE || edge.sourceHandle === EdgeHandleEnum.REJECTED) {
      edgeConfig.weight = 1
    } else if (edge.sourceHandle === EdgeHandleEnum.DONE) {
      edgeConfig.weight = 2
    } else if (edge.sourceHandle === EdgeHandleEnum.LOOP) {
      edgeConfig.weight = 1
    } else if (edge.sourceHandle === EdgeHandleEnum.DEFAULT) {
      // Default/fallback branch gets lowest weight (always last)
      edgeConfig.weight = 1
    } else if (edge.sourceHandle?.startsWith('case_')) {
      // Switch case handles: case_0, case_1, case_2, ...
      // Assign descending weights to preserve vertical order matching handle order
      const caseMatch = edge.sourceHandle.match(/^case_(\d+)$/)
      if (caseMatch) {
        const caseIndex = Number.parseInt(caseMatch[1], 10)
        // Start at weight 50 for case_0, then 49, 48, ... (always > default weight of 1)
        // Higher starting value ensures strictly decreasing weights even with many cases
        edgeConfig.weight = Math.max(50 - caseIndex, 2)
      }
    }

    g.setEdge(edge.source, edge.target, edgeConfig)
  })
  realNodes.forEach((node) => {
    // Use actual node width for Dagre layout
    // Loop body nodes are positioned manually, so we don't need to account for them in Dagre's width calculation
    // This ensures consistent edge spacing between all nodes
    const width = node.measured?.width ?? 0
    g.setNode(node.id, {
      ...node,
      width,
      height: node.measured?.height ?? 0,
    })
  })

  Dagre.layout(g)

  // Calculate positions for loop body nodes (right and below the loop node)
  const loopBodyPositions = calculateLoopBodyPositions(loopBodies, realNodes, g)

  // Build map of branch nodes and their desired target ordering
  const branchNodeOrdering = buildBranchNodeOrdering(realEdges, realNodes)

  return {
    nodes: nodes.map((node) => {
      if (!node.id.startsWith('placeholder-')) {
        const position = getNodeLabel(g, node.id)
        const nodeWidth = node.measured?.width ?? 0
        const nodeHeight = node.measured?.height ?? 0
        let x = position.x - nodeWidth / 2
        let y = position.y - nodeHeight / 2

        // Use pre-calculated positions for loop body nodes
        if (loopBodyNodes.has(node.id)) {
          const centeredPos = loopBodyPositions.get(node.id)
          if (centeredPos) {
            x = centeredPos.x
            y = centeredPos.y
          }
        } else {
          // Adjust Y position for branch target nodes to maintain visual order
          // Skip loop body nodes since they're already positioned by calculateLoopBodyPositions
          y = correctBranchNodePosition({ nodeId: node.id, baseY: y, nodeHeight, branchNodeOrdering, g })
        }

        // Add className for loop body nodes to match loop node width
        const isLoopBodyNode = loopBodyNodes.has(node.id)
        return {
          ...node,
          position: { x, y },
          className: isLoopBodyNode ? 'min-w-[300px]' : node.className,
        }
      }
      return node
    }),
    edges: edges.map((edge) => ({ ...edge, markerEnd })),
  }
}
