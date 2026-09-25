import { type Dispatch, useEffect } from 'react'

import type { BuilderAction } from '../builderReducer'
import { usePendingBuilderNodeAddStore } from '../pendingBuilderNodeAddStore'

type UseApplyPendingBuilderNodeAddOptions = {
  canEdit: boolean
  isLoading: boolean
  viewingVersion: number | null
}

/**
 * Opens the add-step editor when the command palette queued a builder step.
 * Ignores the request while permissions are loading; drops it on read-only
 * or historical version views so a later editable session is not surprised.
 *
 * The command palette lives outside BuilderContent, so this effect is the
 * event bridge — not derived render state.
 */
export function useApplyPendingBuilderNodeAdd(
  dispatch: Dispatch<BuilderAction>,
  { canEdit, isLoading, viewingVersion }: UseApplyPendingBuilderNodeAddOptions
): void {
  const pending = usePendingBuilderNodeAddStore((state) => state.pending)
  const take = usePendingBuilderNodeAddStore((state) => state.take)

  // The pending store is an external event (palette selection), not a prop to sync.
  /* eslint-disable reactYouMightNotNeedAnEffect/no-event-handler, reactYouMightNotNeedAnEffect/no-pass-data-to-parent -- cross-tree command-palette bridge */
  useEffect(() => {
    if (!pending || isLoading) return
    if (!canEdit || viewingVersion != null) {
      take()
      return
    }
    dispatch({ type: 'OPEN_NODE_EDITOR_ADD', payload: pending })
    take()
  }, [pending, isLoading, canEdit, viewingVersion, dispatch, take])
  /* eslint-enable reactYouMightNotNeedAnEffect/no-event-handler, reactYouMightNotNeedAnEffect/no-pass-data-to-parent */
}
