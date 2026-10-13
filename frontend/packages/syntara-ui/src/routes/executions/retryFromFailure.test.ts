import { ExecutionStatusEnum } from '@syntara/contracts'

import {
  canConfirmRetryFromFailure,
  describeRetryScope,
  eligibleRetryPointIds,
  isRetryFromFailureEligible,
  type RetryFromFailurePreview,
} from './retryFromFailure'

function preview(overrides: Partial<RetryFromFailurePreview> = {}): RetryFromFailurePreview {
  return {
    eligible: true,
    eligible_point_ids: ['node-a'],
    total_step_count: 3,
    ...overrides,
  }
}

describe('isRetryFromFailureEligible', () => {
  it.each([ExecutionStatusEnum.FAILED, ExecutionStatusEnum.COMPLETED_WITH_ERRORS])(
    'allows a retry from failure for %s',
    (status) => {
      expect(isRetryFromFailureEligible(status)).toBe(true)
    }
  )

  it.each([
    ExecutionStatusEnum.COMPLETED,
    ExecutionStatusEnum.CANCELLED,
    ExecutionStatusEnum.RUNNING,
    ExecutionStatusEnum.PENDING,
    ExecutionStatusEnum.PAUSED,
  ])('refuses a retry from failure for %s', (status) => {
    expect(isRetryFromFailureEligible(status)).toBe(false)
  })

  it('refuses a retry from failure for a test execution even when failed', () => {
    expect(isRetryFromFailureEligible(ExecutionStatusEnum.FAILED, 'test')).toBe(false)
  })

  it('refuses a retry from failure when status is missing', () => {
    expect(isRetryFromFailureEligible(null)).toBe(false)
    expect(isRetryFromFailureEligible(undefined)).toBe(false)
  })
})

describe('eligibleRetryPointIds', () => {
  it('returns the backend-reported points', () => {
    expect(eligibleRetryPointIds(preview({ eligible_point_ids: ['a', 'b'] }))).toEqual(['a', 'b'])
  })

  it('returns an empty list when the preview is absent', () => {
    expect(eligibleRetryPointIds(undefined)).toEqual([])
  })
})

describe('describeRetryScope', () => {
  it('describes a single failure point re-running one step', () => {
    expect(describeRetryScope(preview({ eligible_point_ids: ['a'], total_step_count: 1 }))).toBe(
      'Retrying will resume at 1 failure point and re-run 1 step. Steps that already completed keep their output.'
    )
  })

  it('pluralizes multiple failure points and steps', () => {
    expect(describeRetryScope(preview({ eligible_point_ids: ['a', 'b'], total_step_count: 5 }))).toBe(
      'Retrying will resume at 2 failure points and re-run 5 steps. Steps that already completed keep their output.'
    )
  })

  it('states that nothing needs re-running when the total is zero', () => {
    expect(describeRetryScope(preview({ eligible_point_ids: ['a'], total_step_count: 0 }))).toBe(
      'Retrying will resume at 1 failure point. No additional steps need to re-run.'
    )
  })

  it('reports when no failure points were found', () => {
    expect(describeRetryScope(preview({ eligible_point_ids: [], total_step_count: 0 }))).toBe(
      'No failed steps were found to retry from.'
    )
  })

  it('falls back to the no-failure-points copy when the preview is absent', () => {
    expect(describeRetryScope(undefined)).toBe('No failed steps were found to retry from.')
  })
})

describe('canConfirmRetryFromFailure', () => {
  it('allows confirming an eligible preview with at least one point', () => {
    expect(canConfirmRetryFromFailure(preview(), false, false)).toBe(true)
  })

  it('blocks confirming while the preview is loading', () => {
    expect(canConfirmRetryFromFailure(preview(), true, false)).toBe(false)
  })

  it('blocks confirming when the preview errored', () => {
    expect(canConfirmRetryFromFailure(preview(), false, true)).toBe(false)
  })

  it('blocks confirming an ineligible preview', () => {
    expect(canConfirmRetryFromFailure(preview({ eligible: false }), false, false)).toBe(false)
  })

  it('blocks confirming an eligible preview that reports no retry points', () => {
    expect(canConfirmRetryFromFailure(preview({ eligible_point_ids: [] }), false, false)).toBe(false)
  })

  it('blocks confirming when there is no preview', () => {
    expect(canConfirmRetryFromFailure(undefined, false, false)).toBe(false)
  })
})
