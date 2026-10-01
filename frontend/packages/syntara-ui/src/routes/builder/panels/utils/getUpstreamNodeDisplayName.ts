import { executorMetadata, nodeMetadata } from '../../../workflows/canvas/nodes/nodeMetadata'
import type { UpstreamNodeInfo } from '../hooks/useUpstreamNodes'

/**
 * Resolve the canvas-equivalent type label for an activity/trigger type string.
 * Logic nodes and executors use registry metadata; trigger API types share the Trigger label.
 */
export function getActivityTypeLabel(type: string): string | undefined {
  const nodeLabel = nodeMetadata[type]?.label
  if (nodeLabel) return nodeLabel

  const executorLabel = executorMetadata[type]?.label
  if (executorLabel) return executorLabel

  if (type === 'manual' || type.endsWith('_trigger')) {
    return nodeMetadata.trigger.label
  }

  return undefined
}

/**
 * Display name for Input panel / navigation surfaces — matches canvas SynStepTitle fallback:
 * trimmed custom name, else type label (Converge, Script, …), else id.
 */
export function getUpstreamNodeDisplayName(node: Pick<UpstreamNodeInfo, 'id' | 'name' | 'type'>): string {
  const trimmed = node.name?.trim()
  if (trimmed) return trimmed
  return getActivityTypeLabel(node.type) ?? node.id
}
