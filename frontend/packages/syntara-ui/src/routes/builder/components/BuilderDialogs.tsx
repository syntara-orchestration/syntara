import { Checkbox, Content, Stack, StackItem } from '@patternfly/react-core'
import { useMemo, useEffect, useRef, useState, type Dispatch } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import type { DialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { selectActivities, selectTriggers } from '../../../stores/workflowStoreSelectors'
import { WorkflowDeleteDialog } from '../../workflows/WorkflowDeleteDialog'
import type { BuilderAction } from '../builderReducer'
import { useBuilderImportHandlers, type UseBuilderImportHandlersParams } from '../hooks/useBuilderImportHandlers'
import type { PendingImportData } from '../useWorkflowImportExport'
import { activitiesReferenceTrigger, hasNonEmptyInputSchema } from '../utils/triggerReferenceCheck'
import type { ConflictAction, ConflictInfo } from '../VersionConflictDialog'
import { VersionConflictDialog } from '../VersionConflictDialog'

import { ImportConfirmationDialog } from './ImportConfirmationDialog'
import type { RunStepDialogData, RunStepExecutionCreatedOptions } from './RunStepDialog'
import { RunStepDialog } from './RunStepDialog'
import { RunWorkflowModal } from './RunWorkflowModal'

const RUN_CONFIRM_DISMISSED_KEY = 'syntara-run-workflow-confirm-dismissed'

function getRunConfirmDismissed(): boolean {
  try {
    return localStorage.getItem(RUN_CONFIRM_DISMISSED_KEY) === 'true'
  } catch {
    return false
  }
}

function setRunConfirmDismissed(): void {
  try {
    localStorage.setItem(RUN_CONFIRM_DISMISSED_KEY, 'true')
  } catch {
    // ignore – storage unavailable
  }
}

type BuilderDialogsProps = Readonly<{
  workflowName: string
  workflowId: string | null
  confirmDialogOpen: boolean
  deleteDialogOpen: boolean
  dispatch: Dispatch<BuilderAction>
  handleRunWorkflow: (inputData?: Record<string, unknown>, triggerNodeId?: string) => void
  handleDeleteWorkflow: () => void
  triggerName: string
  triggerNodeId?: string
  triggerInputSchema?: Record<string, unknown>
  pendingImport: PendingImportData | null
  setPendingImport: (data: PendingImportData | null) => void
  importDeps: Omit<
    UseBuilderImportHandlersParams,
    'dispatch' | 'markDirty' | 'showAlert' | 'showSuccess' | 'showError' | 'showInfo'
  >
  runStepDialog: DialogState<RunStepDialogData>
  runStepTriggerNodeId?: string
  onRunStepExecutionCreated?: (executionId: string, options: RunStepExecutionCreatedOptions) => void
  pinnedMockData?: Record<string, Record<string, unknown>>
  conflictDialogProps?: {
    isOpen: boolean
    onClose: () => void
    conflictAction: ConflictAction
    conflictInfo?: ConflictInfo | null
    onSaveAsNewest: (action: ConflictAction) => void
    onDuplicate: (action: ConflictAction) => void
    onRefreshToLatest: () => void
    isLoading: boolean
  }
}>

type UseRunConfirmStateParams = {
  confirmDialogOpen: boolean
  showInputDialog: boolean
  dispatch: Dispatch<BuilderAction>
  handleRunWorkflow: (inputData?: Record<string, unknown>, triggerNodeId?: string) => void
  triggerNodeId?: string
}

function useRunConfirmState({
  confirmDialogOpen,
  showInputDialog,
  dispatch,
  handleRunWorkflow,
  triggerNodeId,
}: UseRunConfirmStateParams) {
  const [confirmedRun, setConfirmedRun] = useState(false)
  const [doNotShowAgain, setDoNotShowAgain] = useState(false)
  const [prevOpen, setPrevOpen] = useState(confirmDialogOpen)

  // getDerivedStateFromProps pattern — reset state on open/close transitions
  if (confirmDialogOpen && !prevOpen) {
    setPrevOpen(true)
    setConfirmedRun(false)
    setDoNotShowAgain(false)
  } else if (!confirmDialogOpen && prevOpen) {
    setPrevOpen(false)
  }

  const skipConfirm = confirmDialogOpen && getRunConfirmDismissed()

  // Auto-run when confirmation is skipped and no input dialog is needed
  const autoRanRef = useRef(false)
  useEffect(() => {
    if (skipConfirm && !showInputDialog && confirmDialogOpen && !autoRanRef.current) {
      autoRanRef.current = true
      handleRunWorkflow(undefined, triggerNodeId)
      dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
    }
    if (!confirmDialogOpen) {
      autoRanRef.current = false
    }
  }, [skipConfirm, showInputDialog, confirmDialogOpen, handleRunWorkflow, dispatch, triggerNodeId])

  return {
    showConfirmStep: confirmDialogOpen && !skipConfirm && !confirmedRun,
    showInputStep: showInputDialog && confirmDialogOpen && (skipConfirm || confirmedRun),
    doNotShowAgain,
    setDoNotShowAgain,
    closeAll: () => {
      dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
      setConfirmedRun(false)
      setDoNotShowAgain(false)
    },
    handleConfirmRun: () => {
      if (doNotShowAgain) setRunConfirmDismissed()
      if (showInputDialog) {
        setConfirmedRun(true)
      } else {
        handleRunWorkflow(undefined, triggerNodeId)
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
      }
    },
  }
}

export function BuilderDialogs({
  workflowName,
  workflowId,
  confirmDialogOpen,
  deleteDialogOpen,
  dispatch,
  handleRunWorkflow,
  handleDeleteWorkflow,
  triggerName,
  triggerNodeId,
  triggerInputSchema,
  pendingImport,
  setPendingImport,
  importDeps,
  runStepDialog,
  runStepTriggerNodeId,
  onRunStepExecutionCreated,
  pinnedMockData,
  conflictDialogProps,
}: BuilderDialogsProps) {
  const isDirty = useWorkflowStore((state) => state.isDirty)
  const markDirty = useWorkflowStore((state) => state.markDirty)
  const { showAlert, showSuccess, showError: showImportError, showInfo } = useAlerts()
  const { handleImportCurrent, handleImportNew, clearPendingImport } = useBuilderImportHandlers(
    { ...importDeps, dispatch, markDirty, showAlert, showSuccess, showError: showImportError, showInfo },
    pendingImport,
    setPendingImport
  )
  const activities = useWorkflowStore(selectActivities)
  const triggers = useWorkflowStore(selectTriggers)
  const triggerNodeIds = useMemo(() => (triggers ?? []).map((t) => t.id).filter(Boolean), [triggers])
  const showInputDialog =
    hasNonEmptyInputSchema(triggerInputSchema) || activitiesReferenceTrigger(activities ?? [], triggerNodeIds)
  const { showConfirmStep, showInputStep, doNotShowAgain, setDoNotShowAgain, closeAll, handleConfirmRun } =
    useRunConfirmState({ confirmDialogOpen, showInputDialog, dispatch, handleRunWorkflow, triggerNodeId })
  return (
    <>
      <SynConfirmationDialog
        isOpen={showConfirmStep}
        onClose={closeAll}
        onConfirm={handleConfirmRun}
        title={`Run ${workflowName}?`}
        confirmLabel={isDirty ? 'Save and run' : 'Run now'}
        aria-labelledby="run-workflow-modal-title"
        aria-describedby="run-workflow-modal-description"
      >
        <Stack hasGutter>
          <StackItem>
            <Content component="p">
              {isDirty
                ? 'You are about to save and run this workflow. Your unsaved changes will be saved before the workflow starts, bypassing its normal trigger conditions.'
                : `You are able to run this automation starting from ${triggerName}. This action will start the workflow immediately, bypassing its normal trigger conditions.`}
            </Content>
          </StackItem>
          <StackItem>
            <Checkbox
              id="run-workflow-do-not-show-again"
              label="Don't show again for all manual workflow runs"
              isChecked={doNotShowAgain}
              onChange={(_event, checked) => setDoNotShowAgain(checked)}
            />
          </StackItem>
        </Stack>
      </SynConfirmationDialog>
      <RunWorkflowModal
        key={showInputStep ? `open-${triggerNodeId ?? ''}` : 'closed'}
        isOpen={showInputStep}
        onClose={closeAll}
        onConfirm={handleRunWorkflow}
        workflowName={workflowName}
        triggerName={triggerName}
        triggerNodeId={triggerNodeId}
        inputSchema={triggerInputSchema}
        workflowId={workflowId}
      />
      <WorkflowDeleteDialog
        isOpen={deleteDialogOpen}
        workflowName={workflowName}
        onClose={() => dispatch({ type: 'SET_DELETE_DIALOG', payload: false })}
        onConfirm={handleDeleteWorkflow}
        aria-labelledby="delete-workflow-modal-title"
        aria-describedby="delete-workflow-modal-body"
      />
      <RunStepDialog
        isOpen={runStepDialog.isOpen}
        onClose={runStepDialog.close}
        onExecutionCreated={onRunStepExecutionCreated}
        nodeId={runStepDialog.item?.nodeId ?? null}
        nodeName={runStepDialog.item?.nodeName ?? ''}
        workflowId={workflowId ?? ''}
        predecessors={runStepDialog.item?.predecessors}
        pinnedMockData={pinnedMockData}
        triggerInputSchema={triggerInputSchema}
        triggerNodeId={runStepTriggerNodeId}
      />
      <ImportConfirmationDialog
        isOpen={pendingImport != null}
        onClose={clearPendingImport}
        onImportCurrent={handleImportCurrent}
        onImportNew={handleImportNew}
        workflowName={pendingImport?.name ?? ''}
        isDirty={isDirty}
        isPending={false}
      />
      {conflictDialogProps && <VersionConflictDialog {...conflictDialogProps} />}
    </>
  )
}
