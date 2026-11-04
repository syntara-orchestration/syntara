import { RunWorkflowModal } from '../builder/components/RunWorkflowModal'

import type { PendingWorkflowRunInput } from './applyResolvedWorkflowRun'
import { FormTriggerRunDialog } from './formTrigger/FormTriggerRunDialog'
import { useWorkflowPermissions } from './useWorkflowPermissions'

type WorkflowListRunInputDialogsProps = Readonly<{
  pendingRunInput: PendingWorkflowRunInput | null
  onClose: () => void
  onConfirmInputs: (inputData: Record<string, unknown>, triggerNodeId?: string) => void
}>

export function WorkflowListRunInputDialogs({
  pendingRunInput,
  onClose,
  onConfirmInputs,
}: WorkflowListRunInputDialogsProps) {
  const runPermissions = useWorkflowPermissions({
    resourceProject: pendingRunInput?.workflow.project_id ?? undefined,
    enabled: pendingRunInput != null,
  })

  if (pendingRunInput?.trigger.formTrigger) {
    return (
      <FormTriggerRunDialog
        key={`form-${pendingRunInput.trigger.triggerNodeId}`}
        isOpen
        onClose={onClose}
        workflowId={pendingRunInput.workflow.id ?? ''}
        workflowName={pendingRunInput.workflow.name ?? ''}
        triggerNodeId={pendingRunInput.trigger.triggerNodeId}
        triggerName={pendingRunInput.trigger.triggerName}
        formTrigger={pendingRunInput.trigger.formTrigger}
        usePublished
        canRun={runPermissions.canRun}
        isCheckingPermissions={runPermissions.isLoading}
        runTooltip={runPermissions.tooltips.run}
      />
    )
  }

  return (
    <RunWorkflowModal
      key={pendingRunInput ? `open-${pendingRunInput.trigger.triggerNodeId}` : 'closed'}
      isOpen={pendingRunInput != null}
      onClose={onClose}
      onConfirm={onConfirmInputs}
      workflowName={pendingRunInput?.workflow.name ?? ''}
      triggerName={pendingRunInput?.trigger.triggerName ?? 'Trigger'}
      triggerNodeId={pendingRunInput?.trigger.triggerNodeId}
      inputSchema={pendingRunInput?.trigger.inputSchema}
      workflowId={pendingRunInput?.workflow.id}
    />
  )
}
