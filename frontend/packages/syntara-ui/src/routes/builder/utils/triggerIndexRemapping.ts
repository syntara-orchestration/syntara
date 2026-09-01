import { buildTriggerNodeId, parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { EdgeConnection } from '../types/edge'

/**
 * Builds a mapping from old trigger indices to new trigger indices after deletion.
 *
 * When triggers are deleted from an array, the indices of remaining triggers shift.
 * This function computes the new index for each remaining trigger.
 *
 * Example: If trigger-1 is deleted, trigger-2 becomes trigger-1, trigger-3 becomes trigger-2, etc.
 *
 * @param deletedIndices - Set of trigger indices that were deleted
 * @param originalTriggerCount - Total number of triggers before deletion
 * @returns Map from old index to new index (only includes triggers that need remapping)
 */
export function buildTriggerIndexRemappping(
  deletedIndices: Set<number>,
  originalTriggerCount: number
): Map<number, number> {
  const triggerIndexRemap = new Map<number, number>()
  let newIndex = 0

  for (let oldIndex = 0; oldIndex < originalTriggerCount; oldIndex++) {
    if (!deletedIndices.has(oldIndex)) {
      // Only add to map if the index actually changed
      if (oldIndex !== newIndex) {
        triggerIndexRemap.set(oldIndex, newIndex)
      }
      newIndex++
    }
  }

  return triggerIndexRemap
}

/**
 * Remaps trigger display IDs in edges after trigger deletion.
 *
 * CRITICAL: When triggers are deleted, trigger array indices shift, causing
 * display IDs like "trigger-1" to point to different triggers. This function
 * updates edge source/target IDs to maintain correct connections.
 *
 * This function is used by both:
 * - useWorkflowStore.ts (for store-level deletions)
 * - useNodeDeletion.ts (for React Flow deletions)
 *
 * @param edges - Array of edges to remap
 * @param triggerIndexRemap - Map from old index to new index
 * @returns Updated edges with remapped trigger IDs
 */
export function remapTriggerIdsInEdges<T extends EdgeConnection>(
  edges: T[],
  triggerIndexRemap: Map<number, number>
): T[] {
  if (triggerIndexRemap.size === 0) {
    return edges
  }

  return edges.map((edge) => {
    let updatedSource = edge.source
    let updatedTarget = edge.target
    let needsUpdate = false

    // Check if source is a trigger display ID that needs remapping
    const sourceTriggerIndex = parseTriggerIndex(edge.source)
    if (sourceTriggerIndex !== undefined) {
      const newIndex = triggerIndexRemap.get(sourceTriggerIndex)
      if (newIndex !== undefined) {
        updatedSource = buildTriggerNodeId(newIndex)
        needsUpdate = true
      }
    }

    // Check if target is a trigger display ID that needs remapping
    const targetTriggerIndex = parseTriggerIndex(edge.target)
    if (targetTriggerIndex !== undefined) {
      const newIndex = triggerIndexRemap.get(targetTriggerIndex)
      if (newIndex !== undefined) {
        updatedTarget = buildTriggerNodeId(newIndex)
        needsUpdate = true
      }
    }

    if (needsUpdate) {
      // Build edge ID: "source-target" or "source-target-handle" for special handles
      const handleSuffix = edge.sourceHandle && edge.sourceHandle !== 'source' ? `-${edge.sourceHandle}` : ''
      const edgeId = `${updatedSource}-${updatedTarget}${handleSuffix}`

      return {
        ...edge,
        id: edgeId,
        source: updatedSource,
        target: updatedTarget,
      }
    }

    return edge
  })
}
