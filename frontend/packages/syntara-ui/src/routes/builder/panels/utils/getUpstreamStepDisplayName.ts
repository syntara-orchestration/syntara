import { executorMetadata, stepMetadata } from '../../../workflows/canvas/nodes/stepMetadata'
import type { UpstreamStepInfo } from '../hooks/useUpstreamSteps'

/**
 * Resolve the canvas-equivalent type label for an activity/trigger type string.
 * Logic nodes and executors use registry metadata; trigger API types share the Trigger label.
 */
export function getActivityTypeLabel(type: string): string | undefined {
  const stepLabel = stepMetadata[type]?.label
  if (stepLabel) return stepLabel

  const executorLabel = executorMetadata[type]?.label
  if (executorLabel) return executorLabel

  if (type === 'manual' || type.endsWith('_trigger')) {
    return stepMetadata.trigger.label
  }

  return undefined
}

/**
 * Display name for Input panel / navigation surfaces — matches canvas SynStepTitle fallback:
 * trimmed custom name, else type label (Converge, Script, …), else id.
 */
export function getUpstreamStepDisplayName(node: Pick<UpstreamStepInfo, 'id' | 'name' | 'type'>): string {
  const trimmed = node.name?.trim()
  if (trimmed) return trimmed
  return getActivityTypeLabel(node.type) ?? node.id
}
