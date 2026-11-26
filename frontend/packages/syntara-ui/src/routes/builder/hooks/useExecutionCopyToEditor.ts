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
  mostRecentRunPanelOpen: boolean
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  showSuccess: (alert: { title: string; description?: string }) => void
}

export function useExecutionCopyToEditor({
  executionCopy,
  isWorkflowInitialized,
  mostRecentExecutionId,
  mostRecentRunPanelOpen,
  dispatch,
  markDirty,
  showSuccess,
}: UseExecutionCopyToEditorOptions): void {
  const contentReplacedForExecutionRef = useRef<string | null>(null)
  const latchedExecutionCopyRef = useRef<ExecutionCopyData | undefined>(undefined)
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow)

  useEffect(() => {
    if (executionCopy) {
      latchedExecutionCopyRef.current = executionCopy
    }
  }, [executionCopy])

  const reducerSynced =
    !!executionCopy && mostRecentExecutionId != null && mostRecentExecutionId === executionCopy.executionId

  useEffect(() => {
    if (executionCopy || mostRecentExecutionId) return
    contentReplacedForExecutionRef.current = null
    latchedExecutionCopyRef.current = undefined
  }, [executionCopy, mostRecentExecutionId])

  useEffect(() => {
    const copy = executionCopy ?? latchedExecutionCopyRef.current
    if (!copy || !currentWorkflow || !isWorkflowInitialized) return
    const contentAlreadyApplied = contentReplacedForExecutionRef.current === copy.executionId
    if (mostRecentExecutionId === copy.executionId && mostRecentRunPanelOpen && contentAlreadyApplied) {
      return
    }

    const timer = window.setTimeout(() => {
      const workflowAtApply = useWorkflowStore.getState().currentWorkflow
      if (!workflowAtApply) return

      let copiedRunActivityIds: string[] | undefined
      const contentAlreadyReplaced = contentReplacedForExecutionRef.current === copy.executionId
      const executionAlreadyInReducer = mostRecentExecutionId === copy.executionId

      if (executionAlreadyInReducer && !mostRecentRunPanelOpen) {
        copiedRunActivityIds = collectCopiedRunActivityIds(workflowAtApply)
        dispatch({
          type: 'SET_MOST_RECENT_EXECUTION',
          payload: {
            executionId: copy.executionId,
            copiedRunActivityIds,
          },
        })
        return
      }

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
  }, [
    executionCopy,
    currentWorkflow,
    isWorkflowInitialized,
    mostRecentExecutionId,
    mostRecentRunPanelOpen,
    dispatch,
    markDirty,
    showSuccess,
  ])

  useEffect(() => {
    if (!reducerSynced) return
    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href)
      if (!url.searchParams.has('fromExecution') && !url.searchParams.has('linkExecution')) return
      url.searchParams.delete('fromExecution')
      url.searchParams.delete('linkExecution')
      window.history.replaceState({}, '', url.pathname + url.search)
      window.setTimeout(() => {
        latchedExecutionCopyRef.current = undefined
      }, 500)
    }, 2_000)
    return () => window.clearTimeout(timer)
  }, [reducerSynced])
}
