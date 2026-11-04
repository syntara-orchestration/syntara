import type { Dispatch, MutableRefObject } from 'react'

import type { BuilderAction } from '../builderReducer'

type AutoSubmitFn = () => Promise<boolean>

export type ResolveStepEditorBeforeVerifyOptions = {
  isNodeEditorOpen: boolean
  nodeEditorMode: 'add' | 'edit' | null
  autoSubmitRef: MutableRefObject<AutoSubmitFn | null>
  dispatch: Dispatch<BuilderAction>
}

/** Flush or block when Verify runs while the step editor is open (matches guarded save behavior). */
export async function resolveStepEditorBeforeVerify({
  isNodeEditorOpen,
  nodeEditorMode,
  autoSubmitRef,
  dispatch,
}: ResolveStepEditorBeforeVerifyOptions): Promise<boolean> {
  if (!isNodeEditorOpen) {
    return true
  }
  if (nodeEditorMode === 'edit' && autoSubmitRef.current) {
    return await autoSubmitRef.current()
  }
  dispatch({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
  return false
}
