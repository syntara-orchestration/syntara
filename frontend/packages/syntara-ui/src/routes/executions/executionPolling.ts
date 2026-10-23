import { ExecutionStatusEnum } from '@syntara/contracts'

/**
 * Poll execution query every 3s while status is pending or running.
 * Paused executions rely on WebSocket for approval state updates —
 * polling during paused would overwhelm the API when multiple
 * approval tests run in parallel (3 CI workers × 3s interval),
 * unless the stream is stale and REST must recover execution state.
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
