import { ExecutionStatusEnum } from '@syntara/contracts'

import {
  canConfirmRetryFromFailure,
  eligibleRetryPointIds,
  getRetryPlanPoints,
  isRetryFromFailureEligible,
  selectedRetryPointId,
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

describe('getRetryPlanPoints', () => {
  it('resolves display names, iteration labels, and backend step counts', () => {
    expect(
      getRetryPlanPoints(
        preview({
          eligible_point_ids: ['node-a', 'node-b#iter-2'],
          step_count_by_eligible_point: { 'node-a': 4, 'node-b#iter-2': 2 },
        }),
        new Map([
          ['node-a', 'First Step'],
          ['node-b', 'Loop Step'],
        ]),
        new Map([
          ['node-a', 'script'],
          ['node-b', 'loop'],
        ])
      )
    ).toEqual([
      { id: 'node-a', name: 'First Step', typeLabel: 'Script', stepCount: 4 },
      { id: 'node-b#iter-2', name: 'Loop Step (Iteration 3)', typeLabel: 'Loop', stepCount: 2 },
    ])
  })

  it('falls back to the source node ID if its display name is unavailable', () => {
    expect(getRetryPlanPoints(preview({ eligible_point_ids: ['unknown-node'] }), new Map())).toEqual([
      { id: 'unknown-node', name: 'unknown-node', typeLabel: 'Step', stepCount: undefined },
    ])
  })
})

describe('selectedRetryPointId', () => {
  it('uses a selected failure activity as a base-node retry point', () => {
    expect(selectedRetryPointId('node-a#iter-3', preview({ eligible_point_ids: ['node-a', 'node-b'] }))).toBe('node-a')
  })

  it('does not turn a non-failure selection into an explicit retry point', () => {
    expect(selectedRetryPointId('completed-node', preview({ eligible_point_ids: ['node-a'] }))).toBeUndefined()
  })

  it('does not allow a sanitized auto-included node to become an explicit retry point', () => {
    expect(
      selectedRetryPointId(
        'sanitized-node',
        preview({ eligible_point_ids: ['failed-node', 'sanitized-node'], auto_included_node_ids: ['sanitized-node'] })
      )
    ).toBeUndefined()
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
