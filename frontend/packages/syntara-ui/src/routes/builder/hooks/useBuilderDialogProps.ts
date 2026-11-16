import type { Dispatch, SetStateAction } from 'react'

import type { DialogState } from '../../../hooks/useDialogState'
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
  selectedTriggerIndex: number
  currentWorkflow: { triggers?: unknown[] } | null
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
}

export function useBuilderDialogProps(params: BuilderDialogPropsParams) {
  const {
    workflowName,
    workflowId,
    confirmDialogOpen,
    deleteDialogOpen,
    selectedTriggerIndex,
    currentWorkflow,
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
  } = params

  const triggers = currentWorkflow?.triggers ?? []
  const selectedTrigger = triggers[selectedTriggerIndex] ?? triggers[0]

  const triggerPred = runStepDialog.item?.predecessors?.find((p) => p.isTrigger)
  const runStepTriggerNodeId = triggerPred
    ? (triggers[parseTriggerIndex(triggerPred.id) ?? -1] as { id?: string } | undefined)?.id
    : undefined

  return {
    workflowName,
    workflowId,
    confirmDialogOpen,
    deleteDialogOpen,
    dispatch,
    handleRunWorkflow,
    handleDeleteWorkflow,
    isDeleting,
    triggerName: (selectedTrigger as { name?: string } | undefined)?.name ?? 'Trigger',
    triggerNodeId: (selectedTrigger as { id?: string } | undefined)?.id,
    triggerInputSchema: ((selectedTrigger as { parameters?: Record<string, unknown> } | undefined)?.parameters
      ?.input_schema ?? undefined) as Record<string, unknown> | undefined,
    runStepDialog,
    runStepTriggerNodeId,
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
    },
    pinnedMockData: pinnedMockDataForDialog,
  }
}
