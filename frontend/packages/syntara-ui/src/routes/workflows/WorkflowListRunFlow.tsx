import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import type { DialogState } from '../../hooks/useDialogState'

import type { PendingWorkflowRunInput } from './applyResolvedWorkflowRun'
import { WorkflowListRunInputDialogs } from './WorkflowListRunInputDialogs'
import { WorkflowListRunResolutionSession } from './WorkflowListRunResolutionSession'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type WorkflowListRunFlowProps = Readonly<{
  runDialog: DialogState<Workflow>
  onRunWorkflow: (workflow: Workflow, inputData?: Record<string, unknown>, triggerNodeId?: string) => void
}>

export function WorkflowListRunFlow({ runDialog, onRunWorkflow }: WorkflowListRunFlowProps) {
  const [pendingRunInput, setPendingRunInput] = useState<PendingWorkflowRunInput | null>(null)

  const closeRunInput = useCallback(() => {
    setPendingRunInput(null)
  }, [])

  const resolutionSessionKey =
    runDialog.isOpen && runDialog.item?.id ? runDialog.item.id : 'workflow-run-resolution-idle'

  return (
    <>
      <WorkflowListRunResolutionSession
        key={resolutionSessionKey}
        runDialog={runDialog}
        onRunWorkflow={onRunWorkflow}
        setPendingRunInput={setPendingRunInput}
        pendingRunInput={pendingRunInput}
      />

      <WorkflowListRunInputDialogs
        pendingRunInput={pendingRunInput}
        onClose={closeRunInput}
        onConfirmInputs={(inputData, triggerNodeId) => {
          if (!pendingRunInput) return
          onRunWorkflow(pendingRunInput.workflow, inputData, triggerNodeId ?? pendingRunInput.trigger.triggerNodeId)
          setPendingRunInput(null)
        }}
      />
    </>
  )
}
