import { isReplayedStep, resolveRetryReplayBaseline } from './replayedNodes'

/** Retry execution was created at 12:00; the source run happened at 11:00. */
const RETRY_CREATED_AT = '2026-10-09T12:00:00Z'
const SOURCE_RUN_START = '2026-10-09T11:00:00Z'
const SOURCE_RUN_END = '2026-10-09T11:05:00Z'
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
  it('flags a step that started before the retry was created', () => {
    expect(isReplayedStep(SOURCE_RUN_START, RETRY_CREATED_AT)).toBe(true)
    expect(isReplayedStep(SOURCE_RUN_END, RETRY_CREATED_AT)).toBe(true)
  })

  it('does not flag a step that started inside the retry window', () => {
    expect(isReplayedStep(RETRY_RUN_START, RETRY_CREATED_AT)).toBe(false)
  })

  it('does not flag a step that started exactly when the retry was created', () => {
    expect(isReplayedStep(RETRY_CREATED_AT, RETRY_CREATED_AT)).toBe(false)
  })

  it('does not flag anything without a baseline', () => {
    expect(isReplayedStep(SOURCE_RUN_START, null)).toBe(false)
    expect(isReplayedStep(SOURCE_RUN_START, undefined)).toBe(false)
  })

  it('does not flag a step that has not started yet', () => {
    expect(isReplayedStep(null, RETRY_CREATED_AT)).toBe(false)
    expect(isReplayedStep(undefined, RETRY_CREATED_AT)).toBe(false)
  })

  it('does not guess when a timestamp is unparseable', () => {
    expect(isReplayedStep('not-a-date', RETRY_CREATED_AT)).toBe(false)
    expect(isReplayedStep(SOURCE_RUN_START, 'not-a-date')).toBe(false)
  })
})
