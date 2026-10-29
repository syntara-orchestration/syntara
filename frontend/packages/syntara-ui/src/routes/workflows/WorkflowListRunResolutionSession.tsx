import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useEffect, useState } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import type { DialogState } from '../../hooks/useDialogState'
import { useShowAfterDelay } from '../../hooks/useShowAfterDelay'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'

import { applyResolvedWorkflowRun, type PendingWorkflowRunInput } from './applyResolvedWorkflowRun'
import { workflowRunSkipsManualRunConfirmation } from './formTrigger/formTriggerRunUtils'
import { WorkflowFormTriggerSelectDialog } from './formTrigger/WorkflowFormTriggerSelectDialog'
import { resolveWorkflowListRunTrigger, type WorkflowRunTrigger } from './resolveWorkflowRunTrigger'
import {
  WORKFLOW_LIST_RUN_PREPARING_DELAY_MS,
  workflowListRunConfirmVisible,
  workflowListRunPreparingCandidate,
} from './workflowListRunResolutionUi'
import { WorkflowRunPreparingModal } from './WorkflowRunPreparingModal'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type WorkflowListRunResolutionSessionProps = Readonly<{
  runDialog: DialogState<Workflow>
  onRunWorkflow: (workflow: Workflow, inputData?: Record<string, unknown>, triggerNodeId?: string) => void
  setPendingRunInput: (value: PendingWorkflowRunInput | null) => void
  pendingRunInput: PendingWorkflowRunInput | null
}>

export function WorkflowListRunResolutionSession({
  runDialog,
  onRunWorkflow,
  setPendingRunInput,
  pendingRunInput,
}: WorkflowListRunResolutionSessionProps) {
  const { showError } = useAlerts()
  const [isResolvingRun, setIsResolvingRun] = useState(true)
  const [runConfirmVisible, setRunConfirmVisible] = useState(false)
  const [resolvedRunTrigger, setResolvedRunTrigger] = useState<WorkflowRunTrigger | null>(null)
  const [formStepSelectVisible, setFormStepSelectVisible] = useState(false)
  const [formStepChoices, setFormStepChoices] = useState<WorkflowRunTrigger[]>([])

  const closeRunDialog = runDialog.close
  const workflowToRun = runDialog.item

  const applyRunCallbacks = useCallback(
    () => ({
      showError,
      onRunWorkflow,
      setPendingRunInput,
      closeRunDialog,
    }),
    [closeRunDialog, onRunWorkflow, setPendingRunInput, showError]
  )

  useEffect(() => {
    if (!runDialog.isOpen || !workflowToRun?.id) {
      return
    }

    let cancelled = false

    detachPromise(
      resolveWorkflowListRunTrigger(workflowToRun)
        .then((resolution) => {
          if (cancelled) return
          if (!resolution) {
            applyResolvedWorkflowRun(workflowToRun, null, applyRunCallbacks())
            return
          }
          if (resolution.kind === 'chooseFormStep') {
            setFormStepChoices(resolution.triggers)
            setFormStepSelectVisible(true)
            return
          }
          const trigger = resolution.trigger
          setResolvedRunTrigger(trigger)
          if (workflowRunSkipsManualRunConfirmation(trigger)) {
            applyResolvedWorkflowRun(workflowToRun, trigger, applyRunCallbacks())
            return
          }
          setRunConfirmVisible(true)
        })
        .catch((error: unknown) => {
          if (cancelled) return
          showError({
            title: 'Cannot run workflow',
            description: error instanceof Error ? error.message : 'Failed to load workflow trigger details',
          })
          closeRunDialog()
        })
        .finally(() => {
          if (!cancelled) {
            setIsResolvingRun(false)
          }
        })
    )

    return () => {
      cancelled = true
    }
  }, [applyRunCallbacks, closeRunDialog, runDialog.isOpen, showError, workflowToRun])

  const handleConfirmRun = useCallback(() => {
    if (!workflowToRun || !resolvedRunTrigger) return
    applyResolvedWorkflowRun(workflowToRun, resolvedRunTrigger, applyRunCallbacks())
  }, [applyRunCallbacks, resolvedRunTrigger, workflowToRun])

  const handleFormStepSelect = useCallback(
    (trigger: WorkflowRunTrigger) => {
      if (!workflowToRun) return
      setFormStepSelectVisible(false)
      setFormStepChoices([])
      applyResolvedWorkflowRun(workflowToRun, trigger, applyRunCallbacks())
    },
    [applyRunCallbacks, workflowToRun]
  )

  const handleFormStepSelectClose = useCallback(() => {
    setFormStepSelectVisible(false)
    setFormStepChoices([])
    closeRunDialog()
  }, [closeRunDialog])

  const preparingCandidate = workflowListRunPreparingCandidate({
    runDialogOpen: runDialog.isOpen,
    hasWorkflow: Boolean(workflowToRun),
    isResolvingRun,
    runConfirmVisible,
    hasPendingRunInput: pendingRunInput != null,
    formStepSelectVisible,
  })
  const preparingRunOpen = useShowAfterDelay(preparingCandidate, WORKFLOW_LIST_RUN_PREPARING_DELAY_MS)

  return (
    <>
      <WorkflowRunPreparingModal isOpen={preparingRunOpen} onClose={runDialog.close} />

      <WorkflowFormTriggerSelectDialog
        isOpen={formStepSelectVisible && runDialog.isOpen}
        triggers={formStepChoices}
        onClose={handleFormStepSelectClose}
        onSelect={handleFormStepSelect}
      />

      <SynConfirmationDialog
        isOpen={workflowListRunConfirmVisible(runDialog.isOpen, runConfirmVisible)}
        onClose={runDialog.close}
        onConfirm={handleConfirmRun}
        title="Run workflow?"
        confirmLabel="Run now"
        confirmLoading={isResolvingRun}
      >
        You are about to manually run the workflow <strong>{runDialog.item?.name}</strong>. This action will start the
        workflow immediately, bypassing its normal trigger conditions.
      </SynConfirmationDialog>
    </>
  )
}
