import { type Dispatch, useLayoutEffect } from 'react'

import type { BuilderAction } from '../builderReducer'
import { usePendingBuilderNodeAddStore } from '../pendingBuilderNodeAddStore'

type UseApplyPendingBuilderNodeAddOptions = {
  canEdit: boolean
  isLoading: boolean
  viewingVersion: number | null
}

/**
 * Registers the open builder as the command-palette step target and publishes
 * whether that canvas can accept an add.
 */
export function useApplyPendingBuilderNodeAdd(
  dispatch: Dispatch<BuilderAction>,
  { canEdit, isLoading, viewingVersion }: UseApplyPendingBuilderNodeAddOptions
): void {
  const canAccept = !isLoading && canEdit && viewingVersion == null

  useLayoutEffect(() => {
    usePendingBuilderNodeAddStore.getState().setCanAcceptStepAdd(isLoading ? null : canAccept)
    return () => {
      usePendingBuilderNodeAddStore.getState().setCanAcceptStepAdd(null)
    }
  }, [canAccept, isLoading])

  useLayoutEffect(() => {
    if (isLoading) {
      usePendingBuilderNodeAddStore.getState().registerApply(null)
      return
    }
    const apply = (request: { nodeTypeId: string; nodeSubtypeId: string | null }) => {
      if (!canAccept) return false
      dispatch({ type: 'OPEN_NODE_EDITOR_ADD', payload: request })
      return true
    }
    usePendingBuilderNodeAddStore.getState().registerApply(apply)
    return () => {
      usePendingBuilderNodeAddStore.getState().registerApply(null)
    }
  }, [canAccept, dispatch, isLoading])
}
