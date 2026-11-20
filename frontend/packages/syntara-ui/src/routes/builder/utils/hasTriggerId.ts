import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'

/** Whether a workflow's trigger list contains the given trigger ID. */
export function hasTriggerId(
  triggers: WorkflowDefinition['triggers'] | undefined,
  triggerId: string | undefined
): boolean {
  if (triggerId === undefined) return false
  return triggers?.some((trigger) => trigger.id === triggerId) ?? false
}
