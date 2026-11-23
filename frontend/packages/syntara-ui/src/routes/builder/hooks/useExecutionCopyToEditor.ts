import { useEffect, useRef, type Dispatch } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { BuilderAction } from '../builderReducer'
import { collectCopiedRunActivityIds } from '../utils/executionState/collectCopiedRunActivityIds'
import { parseImportedDefinition } from '../utils/parseImportedDefinition'

export type ExecutionCopyData = {
  executionId: string
  workflowDefinition: Record<string, unknown>
  preserveWorkflow?: boolean
}

type UseExecutionCopyToEditorOptions = {
  executionCopy: ExecutionCopyData | undefined
  isWorkflowInitialized: boolean
  mostRecentExecutionId: string | null
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  showSuccess: (alert: { title: string; description?: string }) => void
}

export function useExecutionCopyToEditor({
  executionCopy,
  isWorkflowInitialized,
  mostRecentExecutionId,
  dispatch,
  markDirty,
  showSuccess,
}: UseExecutionCopyToEditorOptions): void {
  const contentReplacedForExecutionRef = useRef<string | null>(null)
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow)

  const reducerSynced =
    !!executionCopy && mostRecentExecutionId != null && mostRecentExecutionId === executionCopy.executionId

  useEffect(() => {
    if (!executionCopy) {
      contentReplacedForExecutionRef.current = null
    }
  }, [executionCopy])

  useEffect(() => {
    if (!executionCopy || !currentWorkflow || !isWorkflowInitialized) return
    if (reducerSynced) return

    let copiedRunActivityIds: string[] | undefined
    const contentAlreadyReplaced = contentReplacedForExecutionRef.current === executionCopy.executionId

    if (!executionCopy.preserveWorkflow && !contentAlreadyReplaced) {
      const { workflowDef, edges, nodePositions } = parseImportedDefinition(executionCopy.workflowDefinition)
      useWorkflowStore.getState().replaceWorkflowContent(workflowDef, edges, nodePositions)
      copiedRunActivityIds = collectCopiedRunActivityIds(workflowDef)
      contentReplacedForExecutionRef.current = executionCopy.executionId

      if (workflowDef.name && typeof workflowDef.name === 'string') {
        dispatch({ type: 'SET_WORKFLOW_NAME', payload: workflowDef.name })
      }
      if (workflowDef.description && typeof workflowDef.description === 'string') {
        dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: workflowDef.description })
      }
      markDirty()
      showSuccess({
        title: 'Run copied to editor',
        description: 'The run has been loaded into the editor with pinned runtime data.',
      })
    } else if (executionCopy.preserveWorkflow) {
      // Link execution to current graph — snapshot IDs so newly added nodes get no status
      copiedRunActivityIds = collectCopiedRunActivityIds(currentWorkflow)
    } else {
      copiedRunActivityIds = collectCopiedRunActivityIds(currentWorkflow)
    }

    dispatch({
      type: 'SET_MOST_RECENT_EXECUTION',
      payload: {
        executionId: executionCopy.executionId,
        copiedRunActivityIds,
      },
    })
    const url = new URL(window.location.href)
    url.searchParams.delete('fromExecution')
    url.searchParams.delete('linkExecution')
    window.history.replaceState({}, '', url.pathname + url.search)
  }, [executionCopy, currentWorkflow, isWorkflowInitialized, reducerSynced, dispatch, markDirty, showSuccess])
}
