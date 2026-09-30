import { ExecutionStatusEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { isExecutionRetryable } from './executionRetryable'

describe('isExecutionRetryable', () => {
  it.each([
    ExecutionStatusEnum.COMPLETED,
    ExecutionStatusEnum.COMPLETED_WITH_ERRORS,
    ExecutionStatusEnum.FAILED,
    ExecutionStatusEnum.CANCELLED,
  ])('returns true for terminal status %s', (status) => {
    expect(isExecutionRetryable(status)).toBe(true)
  })

  it.each([ExecutionStatusEnum.PENDING, ExecutionStatusEnum.RUNNING, ExecutionStatusEnum.PAUSED])(
    'returns false for non-terminal status %s',
    (status) => {
      expect(isExecutionRetryable(status)).toBe(false)
    }
  )

  it.each([null, undefined])('returns false for %s', (status) => {
    expect(isExecutionRetryable(status)).toBe(false)
  })

  it.each([
    ExecutionStatusEnum.COMPLETED,
    ExecutionStatusEnum.FAILED,
    ExecutionStatusEnum.CANCELLED,
    ExecutionStatusEnum.DENIED,
  ])('returns false for test mode even with terminal status %s', (status) => {
    expect(isExecutionRetryable(status, 'test')).toBe(false)
  })

  it('returns true for standard mode with terminal status', () => {
    expect(isExecutionRetryable(ExecutionStatusEnum.FAILED, 'standard')).toBe(true)
  })
})
