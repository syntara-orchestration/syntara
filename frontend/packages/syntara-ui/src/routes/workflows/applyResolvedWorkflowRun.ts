import type { WorkflowAPI } from '@syntara/contracts'
import { TriggerTypeEnum } from '@syntara/contracts'

import { workflowRunTriggerRequiresInputCollection } from './formTrigger/formTriggerRunUtils'
import type { WorkflowRunTrigger } from './resolveWorkflowRunTrigger'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

export type PendingWorkflowRunInput = {
  workflow: Workflow
  trigger: WorkflowRunTrigger
}

export function applyResolvedWorkflowRun(
  workflow: Workflow,
  trigger: WorkflowRunTrigger | null,
  callbacks: {
    showError: (opts: { title: string; description: string }) => void
    onRunWorkflow: (workflow: Workflow, inputData?: Record<string, unknown>, triggerNodeId?: string) => void
    setPendingRunInput: (value: PendingWorkflowRunInput | null) => void
    closeRunDialog: () => void
  }
): void {
  if (!trigger) {
    callbacks.showError({ title: 'Cannot run workflow', description: 'Workflow has no triggers configured' })
    callbacks.closeRunDialog()
    return
  }

  if (trigger.triggerType === TriggerTypeEnum.FORM_TRIGGER && !trigger.formTrigger) {
    callbacks.showError({
      title: 'Cannot run workflow',
      description: 'Form trigger has an invalid or empty form definition',
    })
    callbacks.closeRunDialog()
    return
  }

  if (!workflowRunTriggerRequiresInputCollection(trigger)) {
    callbacks.onRunWorkflow(workflow, {}, trigger.triggerNodeId)
    callbacks.closeRunDialog()
    return
  }

  callbacks.setPendingRunInput({ workflow, trigger })
  callbacks.closeRunDialog()
}
