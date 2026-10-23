import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { makeUniqueName } from './nodeNaming'

const DEFAULT_FORM_TRIGGER_ID = 'form'

/** Default workflow trigger id for a new form trigger (`form`, `form2`, …). */
export function getDefaultFormTriggerId(): string {
  const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
  const existingIds = triggers.map((trigger) => trigger.id?.trim()).filter((id): id is string => Boolean(id))
  return makeUniqueName(DEFAULT_FORM_TRIGGER_ID, existingIds)
}
