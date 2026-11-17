import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'

import { ACTIVITY_STATUS } from './executionState/executionHelpers'
import {
  getRetryActivityMarkers,
  isReplayedStep,
  isReusedTriggerInput,
  resolveRetryReplayBaseline,
} from './replayedNodes'

/** Retry execution was created at 12:00; the source run happened at 11:00. */
const RETRY_CREATED_AT = '2026-10-09T12:00:00Z'
const SOURCE_RUN_START = '2026-10-09T11:00:00Z'
const SOURCE_RUN_END = '2026-10-09T11:05:00Z'
const ACTION_NODE_TYPE = ActivityTypeEnum.SCRIPT
/** Step that genuinely ran inside the retry. */
const RETRY_RUN_START = '2026-10-09T12:00:05Z'

describe('resolveRetryReplayBaseline', () => {
  it('returns the execution creation time for a retried execution', () => {
    expect(resolveRetryReplayBaseline(RETRY_CREATED_AT, 'source-exec-1')).toBe(RETRY_CREATED_AT)
  })

  it('returns null for an ordinary execution so no step is ever flagged', () => {
    expect(resolveRetryReplayBaseline(RETRY_CREATED_AT, null)).toBeNull()
    expect(resolveRetryReplayBaseline(RETRY_CREATED_AT, undefined)).toBeNull()
  })

  it('returns null when a retry has no creation time to compare against', () => {
    expect(resolveRetryReplayBaseline(null, 'source-exec-1')).toBeNull()
  })

  it('returns null when there is no execution at all', () => {
    expect(resolveRetryReplayBaseline(undefined, undefined)).toBeNull()
  })
})

describe('isReplayedStep', () => {
  it('flags a completed step that started before the retry was created', () => {
    expect(
      isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(true)
    expect(
      isReplayedStep(SOURCE_RUN_END, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(true)
  })

  it('keeps retained failures separate from reused output when partial data is present', () => {
    const failedActivityWithPartialOutput = {
      startedAt: SOURCE_RUN_START,
      status: ACTIVITY_STATUS.FAILED,
      outputData: { partial_result: 'available' },
    }

    expect(getRetryActivityMarkers(failedActivityWithPartialOutput, RETRY_CREATED_AT, ACTION_NODE_TYPE)).toEqual({
      replayed: false,
      retainedFailure: true,
      triggerInputReused: false,
    })
  })

  it('does not flag a step that failed again during the retry', () => {
    expect(
      isReplayedStep(RETRY_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.FAILED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
  })

  it('does not flag cancelled, skipped, or running steps as reused output', () => {
    expect(
      isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.CANCELLED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
    expect(
      isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.SKIPPED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
    expect(
      isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.RUNNING, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
  })

  it('does not flag a completed step that started inside the retry window', () => {
    expect(
      isReplayedStep(RETRY_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
  })

  it('does not flag a completed step that started exactly when the retry was created', () => {
    expect(
      isReplayedStep(RETRY_CREATED_AT, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
  })

  it('never flags a trigger node as reused output', () => {
    expect(
      isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, {
        nodeType: TriggerTypeEnum.MANUAL_TRIGGER,
      })
    ).toBe(false)
  })

  it('identifies original trigger input separately from reused output', () => {
    expect(isReusedTriggerInput(SOURCE_RUN_START, RETRY_CREATED_AT, TriggerTypeEnum.MANUAL_TRIGGER)).toBe(true)
    expect(
      getRetryActivityMarkers(
        { startedAt: SOURCE_RUN_START, status: ACTIVITY_STATUS.COMPLETED },
        RETRY_CREATED_AT,
        TriggerTypeEnum.MANUAL_TRIGGER
      )
    ).toEqual({ replayed: false, retainedFailure: false, triggerInputReused: true })
  })

  it('does not guess retry markers when the node type is missing', () => {
    expect(
      getRetryActivityMarkers({ startedAt: SOURCE_RUN_START, status: ACTIVITY_STATUS.COMPLETED }, RETRY_CREATED_AT)
    ).toEqual({ replayed: false, retainedFailure: false, triggerInputReused: false })
    expect(
      getRetryActivityMarkers({ startedAt: SOURCE_RUN_START, status: ACTIVITY_STATUS.FAILED }, RETRY_CREATED_AT)
    ).toEqual({ replayed: false, retainedFailure: false, triggerInputReused: false })
  })

  it('does not flag anything without a baseline', () => {
    expect(isReplayedStep(SOURCE_RUN_START, null, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })).toBe(
      false
    )
    expect(isReplayedStep(SOURCE_RUN_START, undefined, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })).toBe(
      false
    )
  })

  it('does not flag a step that has not started yet', () => {
    expect(isReplayedStep(null, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })).toBe(
      false
    )
    expect(isReplayedStep(undefined, RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })).toBe(
      false
    )
  })

  it('does not guess when a timestamp is unparseable', () => {
    expect(
      isReplayedStep('not-a-date', RETRY_CREATED_AT, ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
    expect(
      isReplayedStep(SOURCE_RUN_START, 'not-a-date', ACTIVITY_STATUS.COMPLETED, { nodeType: ACTION_NODE_TYPE })
    ).toBe(false)
  })
})
