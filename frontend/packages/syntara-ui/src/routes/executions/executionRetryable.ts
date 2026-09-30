import { ExecutionStatusEnum } from '@syntara/contracts'
import type { ExecutionStatus } from '@syntara/contracts'

const RETRYABLE_STATUSES = new Set<ExecutionStatus>([
  ExecutionStatusEnum.COMPLETED,
  ExecutionStatusEnum.COMPLETED_WITH_ERRORS,
  ExecutionStatusEnum.FAILED,
  ExecutionStatusEnum.CANCELLED,
  ExecutionStatusEnum.DENIED,
])

export function isExecutionRetryable(status: ExecutionStatus | null | undefined, mode?: string | null): boolean {
  if (!status) return false
  if (mode === 'test') return false
  return RETRYABLE_STATUSES.has(status)
}
