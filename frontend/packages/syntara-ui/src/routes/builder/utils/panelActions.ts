import type { Dispatch } from 'react'

import type { BuilderAction } from '../builderReducer'

/**
 * Creates a handler for opening the add step panel from the step details panel.
 * This allows adding a step after a specific source node with an optional source handle.
 */
export function createAddStepHandler(dispatch: Dispatch<BuilderAction>) {
  return (sourceNodeId: string, sourceHandle?: string) => {
    dispatch({
      type: 'OPEN_ADD_NODE_PANEL',
      payload: { sourceNodeId, replacementNodeId: null, sourceHandle },
    })
  }
}
