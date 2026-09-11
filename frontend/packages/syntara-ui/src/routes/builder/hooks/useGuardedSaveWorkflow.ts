import { useCallback, type Dispatch, type MutableRefObject } from 'react'

import type { BuilderAction } from '../builderReducer'

type AutoSubmitFn = () => Promise<boolean>

type UseGuardedSaveWorkflowOptions = {
  handleSaveWorkflow: (options?: { expectedVersionOverride?: number }) => Promise<boolean>
  isNodeEditorOpen: boolean
  nodeEditorMode: 'add' | 'edit' | null
  autoSubmitRef: MutableRefObject<AutoSubmitFn | null>
  dispatch: Dispatch<BuilderAction>
}

export function useGuardedSaveWorkflow({
  handleSaveWorkflow,
  isNodeEditorOpen,
  nodeEditorMode,
  autoSubmitRef,
  dispatch,
}: UseGuardedSaveWorkflowOptions) {
  return useCallback(
    async (options?: { expectedVersionOverride?: number }): Promise<boolean> => {
      if (isNodeEditorOpen) {
        if (nodeEditorMode === 'edit' && autoSubmitRef.current) {
          const submitted = await autoSubmitRef.current()
          if (submitted) return handleSaveWorkflow(options)
          return false
        }
        dispatch({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
        return false
      }
      return handleSaveWorkflow(options)
    },
    [isNodeEditorOpen, nodeEditorMode, handleSaveWorkflow, dispatch, autoSubmitRef]
  )
}
