/**
 * Distinguish steps that reused a previous run's output from steps that ran
 * fresh in the current retry.
 *
 * The retry engine records a replayed completed step with the *source* run's
 * `started_at` / `completed_at`, so a completed step whose start precedes the
 * retry execution's own creation never ran in that execution — it reused the
 * source run's output. A retained failure can also have reusable partial
 * output; only mark it when that output is present. The retry endpoint also
 * re-validates independently, so this is a display-only signal and never gates
 * behaviour.
 */

import { TriggerTypeEnum } from '@syntara/contracts'

import { ACTIVITY_STATUS } from './executionState/executionHelpers'

const TRIGGER_TYPES = new Set<string>(Object.values(TriggerTypeEnum))

function isTriggerNodeType(nodeType: string | null | undefined): boolean {
  return nodeType != null && TRIGGER_TYPES.has(nodeType)
}

function predatesRetry(startedAt: string | null | undefined, replayBaselineAt: string | null | undefined): boolean {
  if (!replayBaselineAt || !startedAt) return false

  const started = Date.parse(startedAt)
  const baseline = Date.parse(replayBaselineAt)
  if (Number.isNaN(started) || Number.isNaN(baseline)) return false

  return started < baseline
}

/**
 * The timestamp replayed steps predate, or `null` when this execution is not a
 * retry and therefore has no replayed steps to show.
 */
export function resolveRetryReplayBaseline(
  executionCreatedAt: string | null | undefined,
  retriedFromExecutionId: string | null | undefined
): string | null {
  if (!retriedFromExecutionId) return null
  return executionCreatedAt ?? null
}

/**
 * Whether a step reused output from a previous run rather than running.
 *
 * Returns `false` whenever the answer is not provable — no baseline, no start
 * time (the step has not run yet), an unparseable timestamp, or a status that
 * cannot have restored output. A failed step needs nonempty output data because
 * it can be retained with partial output.
 */
export function isReplayedStep(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined,
  status: string | null | undefined,
  options?: { outputData?: Record<string, unknown> | null; nodeType?: string | null }
): boolean {
  const { outputData, nodeType } = options ?? {}
  if (isTriggerNodeType(nodeType)) return false

  const hasReusableStatus =
    status === ACTIVITY_STATUS.COMPLETED ||
    (status === ACTIVITY_STATUS.FAILED && outputData != null && Object.keys(outputData).length > 0)
  if (!hasReusableStatus) return false

  return predatesRetry(startedAt, replayBaselineAt)
}

/** Whether a trigger used the source run's input while executing again in this retry. */
export function isReusedTriggerInput(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined,
  nodeType?: string | null
): boolean {
  return isTriggerNodeType(nodeType) && predatesRetry(startedAt, replayBaselineAt)
}

/** Classify the retry markers for an activity row or canvas node. */
export function getRetryActivityMarkers(
  state:
    | {
        startedAt?: string | null
        status?: string | null
        outputData?: Record<string, unknown> | null
      }
    | undefined,
  replayBaselineAt: string | null | undefined,
  nodeType?: string | null
): { replayed: boolean; retainedFailure: boolean; triggerInputReused: boolean } {
  const { startedAt, status, outputData } = state ?? {}
  return {
    replayed: isReplayedStep(startedAt, replayBaselineAt, status, { outputData, nodeType }),
    retainedFailure: isRetainedFailure(startedAt, replayBaselineAt, status, nodeType),
    triggerInputReused: isReusedTriggerInput(startedAt, replayBaselineAt, nodeType),
  }
}

/** Whether a failed step still shows the failure from the source run. */
export function isRetainedFailure(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined,
  status: string | null | undefined,
  nodeType?: string | null
): boolean {
  return status === ACTIVITY_STATUS.FAILED && !isTriggerNodeType(nodeType) && predatesRetry(startedAt, replayBaselineAt)
}
