/**
 * Helpers for matching form prompt records to canvas / activity IDs.
 *
 * `prompt_node_id` is the canvas node ID. Loop identity is `loop_iteration_path`.
 */

import { canvasNodeIdFromApprovalNodeId } from '../../approvals/approvalNodeId'
import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import type { ActivityState } from '../../workflows/execution/types'
import { latestActivityStateForCanvasNode, parseCompositeKey } from '../../workflows/execution/utils/activityState'

export { canvasNodeIdFromApprovalNodeId as canvasNodeIdFromPromptNodeId }

type FormPromptNodeRef = {
  prompt_node_id: string
  status?: string
  loop_iteration_path?: number[]
  temporal_activity_id?: string
}

const LOOP_ITER_CHAIN = /(?:_iter_\d+)+$/

function suffixIterationKey(promptNodeId: string): number[] {
  const chain = LOOP_ITER_CHAIN.exec(promptNodeId)?.[0] ?? ''
  const indices: number[] = []
  const iterNum = /_iter_(\d+)/g
  let match = iterNum.exec(chain)
  while (match !== null) {
    indices.push(Number(match[1]))
    match = iterNum.exec(chain)
  }
  return indices
}

export function formPromptIterationSortKey(prompt: FormPromptNodeRef): number[] {
  if (prompt.loop_iteration_path && prompt.loop_iteration_path.length > 0) {
    return prompt.loop_iteration_path
  }
  return suffixIterationKey(prompt.prompt_node_id)
}

export function compareFormPromptIterationKeys(left: number[], right: number[]): number {
  const len = Math.max(left.length, right.length)
  for (let i = 0; i < len; i++) {
    const diff = (left[i] ?? -1) - (right[i] ?? -1)
    if (diff !== 0) return diff
  }
  return 0
}

function pickLatestLoopPrompt<T extends FormPromptNodeRef>(matches: T[]): T | undefined {
  if (matches.length === 0) return undefined
  const pending = matches.filter((prompt) => prompt.status === 'pending')
  const pool = pending.length > 0 ? pending : matches
  const [latest, ...rest] = pool
  if (latest === undefined) return undefined
  return rest.reduce(
    (best, current) =>
      compareFormPromptIterationKeys(formPromptIterationSortKey(current), formPromptIterationSortKey(best)) >= 0
        ? current
        : best,
    latest
  )
}

export function matchesPromptNodeId(promptNodeId: string, canvasOrActivityId: string): boolean {
  return canvasNodeIdFromApprovalNodeId(promptNodeId) === canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
}

function findByTemporalActivityId<T extends FormPromptNodeRef>(
  prompts: T[],
  canvasOrActivityId: string
): T | undefined {
  const direct = prompts.find((prompt) => prompt.temporal_activity_id === canvasOrActivityId)
  if (direct) return direct

  const { baseId, iteration } = parseCompositeKey(canvasOrActivityId)
  if (iteration === undefined) return undefined

  const singleIterTemporalId = `${baseId}_iter_${iteration}`
  const fromComposite = prompts.find((prompt) => prompt.temporal_activity_id === singleIterTemporalId)
  if (fromComposite) return fromComposite

  return prompts.find(
    (prompt) =>
      typeof prompt.temporal_activity_id === 'string' &&
      matchesPromptNodeId(prompt.temporal_activity_id, canvasOrActivityId)
  )
}

export function findFormPromptForCanvasNode<T extends FormPromptNodeRef>(
  prompts: T[],
  canvasOrActivityId: string
): T | undefined {
  const byTemporal = findByTemporalActivityId(prompts, canvasOrActivityId)
  if (byTemporal) return byTemporal

  const canvasId = canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
  if (canvasOrActivityId !== canvasId) {
    const exactSuffixed = prompts.find((prompt) => prompt.prompt_node_id === canvasOrActivityId)
    if (exactSuffixed) return exactSuffixed
  }
  return pickLatestLoopPrompt(
    prompts.filter((prompt) => matchesPromptNodeId(prompt.prompt_node_id, canvasOrActivityId))
  )
}

export function findFormPromptIndexForCanvasNode<T extends FormPromptNodeRef>(
  prompts: T[],
  canvasOrActivityId: string
): number {
  const match = findFormPromptForCanvasNode(prompts, canvasOrActivityId)
  return match === undefined ? -1 : prompts.indexOf(match)
}

/** Candidate IDs to match canvas clicks, activity rows, and Temporal activity keys. */
export function resolveFormPromptLookupKeys(
  canvasOrActivityId: string,
  activityStates?: ReadonlyMap<string, ActivityState>
): string[] {
  const keys = new Set<string>()
  keys.add(canvasOrActivityId)
  keys.add(canvasNodeIdFromApprovalNodeId(canvasOrActivityId))

  const canvasId = canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
  if (activityStates) {
    for (const activityKey of activityStates.keys()) {
      const { baseId } = parseCompositeKey(activityKey)
      if (
        activityKey === canvasOrActivityId ||
        baseId === canvasOrActivityId ||
        baseId === canvasId ||
        matchesPromptNodeId(baseId, canvasOrActivityId) ||
        matchesPromptNodeId(activityKey, canvasOrActivityId)
      ) {
        keys.add(activityKey)
        keys.add(baseId)
      }
    }
  }

  return [...keys]
}

export function findFormPromptIndexForLookupKeys<T extends FormPromptNodeRef>(
  prompts: T[],
  lookupKeys: readonly string[]
): number {
  for (const key of lookupKeys) {
    const index = findFormPromptIndexForCanvasNode(prompts, key)
    if (index >= 0) return index
  }
  return -1
}

type FormPromptWaitingTimeSource = {
  prompt_node_id: string
  temporal_activity_id?: string
  created_at?: string | null
}

/** When the form step entered waiting (resets each run); prefers live activity state over DB created_at. */
export function resolveFormPromptWaitingStartedAt(
  prompt: FormPromptWaitingTimeSource,
  activityStates: ReadonlyMap<string, ActivityState>
): string | null {
  const lookupKeys = new Set(resolveFormPromptLookupKeys(prompt.prompt_node_id, activityStates))
  if (prompt.temporal_activity_id) {
    lookupKeys.add(prompt.temporal_activity_id)
  }

  for (const key of lookupKeys) {
    const direct = activityStates.get(key)
    if (direct?.status === ACTIVITY_STATUS.WAITING && direct.startedAt) {
      return direct.startedAt
    }
    const canvasId = canvasNodeIdFromApprovalNodeId(key)
    const latest = latestActivityStateForCanvasNode(activityStates, canvasId)
    if (latest?.status === ACTIVITY_STATUS.WAITING && latest.startedAt) {
      return latest.startedAt
    }
  }

  return prompt.created_at ?? null
}

export function lookupMapByPromptNodeId<T>(
  map: ReadonlyMap<string, T> | undefined,
  promptNodeId: string | null | undefined
): T | undefined {
  if (!map || !promptNodeId) return undefined
  const canvasId = canvasNodeIdFromApprovalNodeId(promptNodeId)
  return map.get(canvasId) ?? map.get(promptNodeId)
}
