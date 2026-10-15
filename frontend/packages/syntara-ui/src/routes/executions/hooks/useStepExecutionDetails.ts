import type { ExecutionsAPI } from '@syntara/contracts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { executionsClient } from '../../../client'
import { getLoadedShikiService, loadShikiService } from '../../../components/details/shiki-service-loader'
import { detachPromise } from '../../../utils/detachPromise'
import type { ActivityStatus } from '../../workflows/execution/types'

type StepExecutionDetails = {
  /** Resolved config values passed to the activity at runtime */
  inputData: Record<string, unknown> | null
  /** Activity results after output mapping */
  outputData: Record<string, unknown> | null
  isLoading: boolean
  error: unknown
  refetch: () => Promise<unknown>
}

/**
 * Fetches execution details (input/output data) for a specific workflow step.
 *
 * Uses the `activity_name` query parameter for server-side filtering,
 * so only the matching activity is returned from the API.
 *
 * When `activityStatus` changes (e.g. from WebSocket updates), the query
 * refetches so the Parameters/Output panes stay current.
 */
export function useStepExecutionDetails(
  stepId: string,
  executionId: string | null | undefined,
  activityStatus?: ActivityStatus
): StepExecutionDetails {
  // Preload outside the query; this selector exposes cached data once Shiki is ready.
  const [isShikiSettled, setIsShikiSettled] = useState(() => getLoadedShikiService()?.isShikiReady('json') ?? false)
  const selectActivityResponse = useCallback(
    (response: ExecutionsAPI.components['schemas']['ActivityExecutionListResponse']) =>
      isShikiSettled ? response : undefined,
    [isShikiSettled]
  )

  useEffect(() => {
    if (isShikiSettled || !executionId || !stepId) return

    let isCurrent = true
    const settlePreload = () => {
      if (isCurrent) setIsShikiSettled(true)
    }
    detachPromise(
      loadShikiService()
        .then(({ preloadShiki }) => preloadShiki('json'))
        .then(settlePreload, settlePreload)
    )

    return () => {
      isCurrent = false
    }
  }, [executionId, isShikiSettled, stepId])
  const queryResult = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/activities',
    {
      params: {
        path: { execution_id: executionId ?? '' },
        query: { activity_name: stepId, limit: 1 },
      },
    },
    { enabled: !!executionId && !!stepId, select: selectActivityResponse }
  )

  const { data, isLoading, isSuccess, error, refetch } = queryResult

  const prevStatusRef = useRef(activityStatus)
  useEffect(() => {
    if (prevStatusRef.current !== activityStatus) {
      prevStatusRef.current = activityStatus
      detachPromise(refetch())
    }
  }, [activityStatus, refetch])

  return useMemo(() => {
    if (!data) {
      return {
        inputData: null,
        outputData: null,
        isLoading: isLoading || (isSuccess && !isShikiSettled),
        error,
        refetch,
      }
    }

    const activity = data.resources?.[0]

    // Contract types input_data as Record<string, never> — the runtime values
    // are arbitrary JSON objects, so we widen to Record<string, unknown>.
    // output_data is already typed as Record<string, unknown> | null in the contract.
    return {
      inputData: activity?.input_data ?? null,
      outputData: activity?.output_data ?? null,
      isLoading: isLoading || (isSuccess && !isShikiSettled),
      error,
      refetch,
    }
  }, [data, error, isLoading, isShikiSettled, isSuccess, refetch])
}
