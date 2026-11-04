import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import type { ActivityState } from '../../workflows/execution/types'
import { latestActivityStateForCanvasNode } from '../../workflows/execution/utils/activityState'

import { canvasNodeIdFromPromptNodeId, resolveFormPromptLookupKeys } from './formPromptNodeId'

export type FormPromptActivitySnapshot = {
  status?: string
  errorDetails?: string | null
}

/** Latest execution activity state for a form prompt canvas or Temporal activity id. */
export function resolveFormPromptActivitySnapshot(
  canvasOrActivityId: string,
  activityStates: ReadonlyMap<string, ActivityState>
): FormPromptActivitySnapshot | undefined {
  const lookupKeys = resolveFormPromptLookupKeys(canvasOrActivityId, activityStates)
  let best: ActivityState | undefined

  for (const key of lookupKeys) {
    const direct = activityStates.get(key)
    if (direct && (!best || rankActivityState(direct) > rankActivityState(best))) {
      best = direct
    }
    const canvasId = canvasNodeIdFromPromptNodeId(key)
    const latest = latestActivityStateForCanvasNode(activityStates, canvasId)
    if (latest && (!best || rankActivityState(latest) > rankActivityState(best))) {
      best = latest
    }
  }

  if (!best) {
    return undefined
  }

  return {
    status: best.status,
    errorDetails: best.errorDetails ?? null,
  }
}

function rankActivityState(state: ActivityState): number {
  if (state.status === ACTIVITY_STATUS.FAILED) return 4
  if (state.status === ACTIVITY_STATUS.WAITING) return 3
  if (state.status === ACTIVITY_STATUS.RUNNING || state.status === ACTIVITY_STATUS.RETRYING) return 2
  if (state.status === ACTIVITY_STATUS.COMPLETED) return 1
  return 0
}

/** True when this form step is still awaiting a response (respond panel should open). */
export function isFormPromptActivityWaiting(
  canvasOrActivityId: string,
  activityStates: ReadonlyMap<string, ActivityState>
): boolean {
  return resolveFormPromptActivitySnapshot(canvasOrActivityId, activityStates)?.status === ACTIVITY_STATUS.WAITING
}
