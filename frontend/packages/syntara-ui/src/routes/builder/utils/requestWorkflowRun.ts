import type { Dispatch } from 'react'

import type { BuilderAction } from '../builderReducer'

export function requestWorkflowRun(options: {
  triggerIndex?: number
  triggerNodeId?: string
  requiresInput: boolean
  skipConfirmation: boolean
  dispatch: Dispatch<BuilderAction>
  handleRunWorkflow: (inputData?: Record<string, unknown>, triggerNodeId?: string) => void
}): void {
  const { triggerIndex, triggerNodeId, requiresInput, skipConfirmation, dispatch, handleRunWorkflow } = options

  if (triggerIndex !== undefined) {
    dispatch({ type: 'SET_SELECTED_TRIGGER', payload: triggerIndex })
  }

  if (skipConfirmation && !requiresInput) {
    handleRunWorkflow(undefined, triggerNodeId)
    return
  }

  dispatch({ type: 'SET_CONFIRM_DIALOG', payload: true })
}
