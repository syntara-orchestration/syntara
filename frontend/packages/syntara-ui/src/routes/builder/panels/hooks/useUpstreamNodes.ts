import { useMemo, type ComponentType } from 'react'

import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { selectEdges, selectActivities, selectTriggers } from '../../../../stores/workflowStoreSelectors'
import { buildTriggerNodeId } from '../../../../utils/triggerNodeIds'
import { getUpstreamNodeIds } from '../../utils/edgeHelpers'

export type UpstreamNodeInfo = {
  id: string
  name?: string
  type: string
  icon?: ComponentType<{ className?: string }>
  iconId?: string
}

/**
 * Returns the list of upstream nodes (activities and triggers) that feed data
 * into the node identified by `nodeId`.
 *
 * An upstream node is any activity or trigger that is the source of an edge
 * whose target is `nodeId`. The node itself is excluded from the results
 * even if a self-referencing edge exists.
 */
export function useUpstreamNodes(nodeId: string): UpstreamNodeInfo[] {
  const edges = useWorkflowStore(selectEdges)
  const activities = useWorkflowStore(selectActivities)
  const triggers = useWorkflowStore(selectTriggers)

  return useMemo(() => {
    if (!activities && !triggers) {
      return []
    }

    // Build a lookup map from activities and triggers
    const nodeMap = new Map<string, UpstreamNodeInfo>()

    if (activities) {
      for (const activity of activities) {
        nodeMap.set(activity.id, {
          id: activity.id,
          name: activity.name,
          type: activity.type,
        })
      }
    }

    if (triggers) {
      for (let i = 0; i < triggers.length; i++) {
        const trigger = triggers[i]
        const info: UpstreamNodeInfo = {
          id: trigger.id,
          name: trigger.name,
          type: trigger.type,
        }
        nodeMap.set(trigger.id, info)
        nodeMap.set(buildTriggerNodeId(i), info)
      }
    }

    // BFS traversal to find ALL ancestors in the graph, not just direct predecessors.
    // This lets users reference any upstream node's output (e.g., ${gather_info.stdout_json}
    // from the last node in a long chain).
    const upstreamIds = getUpstreamNodeIds(nodeId, edges)

    const upstreamNodes: UpstreamNodeInfo[] = []
    for (const id of upstreamIds) {
      const node = nodeMap.get(id)
      if (node) {
        upstreamNodes.push(node)
      }
    }

    return upstreamNodes
  }, [edges, activities, triggers, nodeId])
}
