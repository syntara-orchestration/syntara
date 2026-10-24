import { ExecutionStatusEnum } from '@syntara/contracts'

/**
 * Poll execution query every 3s while status is pending or running.
 * Paused executions rely on WebSocket for approval state updates,
 * falling back to polling only while the stream is stale.
 */
export function executionRefetchInterval(
  query: { state: { data?: { status?: string } } },
  isStreamStale = false
): number | false {
  const status = query.state.data?.status
  if (
    !status ||
    status === ExecutionStatusEnum.PENDING ||
    status === ExecutionStatusEnum.RUNNING ||
    (status === ExecutionStatusEnum.PAUSED && isStreamStale)
  ) {
    return 3000
  }
  return false
}
