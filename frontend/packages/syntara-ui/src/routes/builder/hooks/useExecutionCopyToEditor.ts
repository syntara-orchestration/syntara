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

    const copy = executionCopy
    // Macrotask so lifecycle INIT (microtask) always runs first; still re-applies when INIT clears the run id.
    const timer = window.setTimeout(() => {
      const workflowAtApply = useWorkflowStore.getState().currentWorkflow
      if (!workflowAtApply) return

      let copiedRunActivityIds: string[] | undefined
      const contentAlreadyReplaced = contentReplacedForExecutionRef.current === copy.executionId

      if (!copy.preserveWorkflow && !contentAlreadyReplaced) {
        const { workflowDef, edges, nodePositions } = parseImportedDefinition(copy.workflowDefinition)
        useWorkflowStore.getState().replaceWorkflowContent(workflowDef, edges, nodePositions)
        copiedRunActivityIds = collectCopiedRunActivityIds(workflowDef)
        contentReplacedForExecutionRef.current = copy.executionId

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
      } else if (copy.preserveWorkflow) {
        copiedRunActivityIds = collectCopiedRunActivityIds(workflowAtApply)
      } else {
        copiedRunActivityIds = collectCopiedRunActivityIds(workflowAtApply)
      }

      dispatch({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: {
          executionId: copy.executionId,
          copiedRunActivityIds,
        },
      })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [executionCopy, currentWorkflow, isWorkflowInitialized, reducerSynced, dispatch, markDirty, showSuccess])

  // Clear query params after reducer sync; delay so copy can re-apply if INIT clears the run id first.
  useEffect(() => {
    if (!reducerSynced) return
    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href)
      if (!url.searchParams.has('fromExecution') && !url.searchParams.has('linkExecution')) return
      url.searchParams.delete('fromExecution')
      url.searchParams.delete('linkExecution')
      window.history.replaceState({}, '', url.pathname + url.search)
    }, 2_000)
    return () => window.clearTimeout(timer)
  }, [reducerSynced])
}
