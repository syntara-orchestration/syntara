import type { Dispatch, SetStateAction } from 'react'

import type { DialogState } from '../../../hooks/useDialogState'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { BuilderAction } from '../builderReducer'
import type { RunStepDialogData } from '../components/RunStepDialog'
import type { PendingImportData } from '../useWorkflowImportExport'

import type { UseBuilderSaveWorkflowParams } from './useBuilderSaveWorkflow'

export type BuilderDialogPropsParams = {
  workflowName: string
  workflowId: string | null
  confirmDialogOpen: boolean
  deleteDialogOpen: boolean
  selectedTriggerId?: string
  currentWorkflow: Pick<WorkflowDefinition, 'triggers'> | null
  runWorkflow?: WorkflowDefinition | null
  runReadOnly?: boolean
  dispatch: Dispatch<BuilderAction>
  handleRunWorkflow: (inputData?: Record<string, unknown>, triggerNodeId?: string) => void
  handleDeleteWorkflow: () => void
  isDeleting: boolean
  runStepDialog: DialogState<RunStepDialogData>
  lastRunStepNodeIdRef: React.MutableRefObject<string | null>
  pendingImport: PendingImportData | null
  setPendingImport: Dispatch<SetStateAction<PendingImportData | null>>
  selectedProject: { id: string } | null
  createWorkflow: UseBuilderSaveWorkflowParams['createWorkflow']
  setLocation: (path: string) => void
  pinnedMockDataForDialog: Record<string, Record<string, unknown>> | undefined
  /** Refuses pasting an import containing a blocked step type onto the canvas. */
  getImportRefusal?: (data: PendingImportData) => string | null
}

export function useBuilderDialogProps(params: BuilderDialogPropsParams) {
  const {
    workflowName,
    workflowId,
    confirmDialogOpen,
    deleteDialogOpen,
    selectedTriggerId,
    currentWorkflow,
    runWorkflow,
    runReadOnly,
    dispatch,
    handleRunWorkflow,
    handleDeleteWorkflow,
    isDeleting,
    runStepDialog,
    lastRunStepNodeIdRef,
    pendingImport,
    setPendingImport,
    selectedProject,
    createWorkflow,
    setLocation,
    pinnedMockDataForDialog,
    getImportRefusal,
  } = params

  const selectedTrigger = runWorkflow?.triggers?.find((trigger) => trigger.id === selectedTriggerId)
  const triggerPred = runStepDialog.item?.predecessors?.find((p) => p.isTrigger)
  const stepTrigger = triggerPred ? currentWorkflow?.triggers?.[parseTriggerIndex(triggerPred.id) ?? -1] : undefined

  return {
    workflowName,
    workflowId,
    // The caller already masks this flag when the run dialog goes stale
    // (permission flip or missing selected trigger), so no extra guard here.
    confirmDialogOpen,
    deleteDialogOpen,
    dispatch,
    handleRunWorkflow,
    handleDeleteWorkflow,
    isDeleting,
    triggerName: selectedTrigger?.name ?? 'Trigger',
    triggerNodeId: selectedTrigger?.id,
    triggerInputSchema: getTriggerSchema(selectedTrigger),
    runWorkflow,
    runReadOnly,
    runStepDialog,
    runStepTriggerNodeId: stepTrigger?.id,
    runStepTriggerInputSchema: getTriggerSchema(stepTrigger),
    onRunStepExecutionCreated: (executionId: string, { clearMocksOnComplete }: { clearMocksOnComplete: boolean }) => {
      lastRunStepNodeIdRef.current = clearMocksOnComplete ? (runStepDialog.item?.nodeId ?? null) : null
      dispatch({ type: 'SET_MOST_RECENT_EXECUTION', payload: { executionId } })
    },
    pendingImport,
    setPendingImport,
    importDeps: {
      selectedProject: selectedProject?.id ? { id: selectedProject.id } : null,
      createWorkflow,
      setLocation,
      getImportRefusal,
    },
    pinnedMockData: pinnedMockDataForDialog,
  }
}

function getTriggerSchema(trigger: NonNullable<WorkflowDefinition['triggers']>[number] | undefined) {
  const schema = trigger?.parameters?.input_schema
  if (typeof schema === 'object' && schema !== null && !Array.isArray(schema)) return schema as Record<string, unknown>
  return undefined
}
