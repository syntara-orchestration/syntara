import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'

/**
 * Resolve the catalog node-type id for a canvas node (activity or trigger display id).
 */
export function resolveWorkflowNodeTypeId(nodeId: string): string | undefined {
  const state = useWorkflowStore.getState()
  const workflow = state.currentWorkflow
  if (!workflow) {
    return undefined
  }

  const activity = workflow.workflow.activities.find((entry) => entry.id === nodeId)
  if (activity?.type) {
    return String(activity.type)
  }

  const triggerIndex = parseTriggerIndex(nodeId)
  if (triggerIndex !== undefined) {
    const trigger = workflow.triggers?.[triggerIndex]
    if (trigger?.type) {
      return String(trigger.type)
    }
  }

  const triggerById = workflow.triggers?.find((trigger) => trigger.id === nodeId)
  if (triggerById?.type) {
    return String(triggerById.type)
  }

  return undefined
}
