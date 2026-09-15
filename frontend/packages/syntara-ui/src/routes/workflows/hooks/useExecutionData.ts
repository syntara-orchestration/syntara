/**
 * Execution Data Hook
 *
 * React hook for fetching execution data via REST API.
 * Loads initial state for execution visualization including workflow definition and activities.
 */

import { useEffect } from 'react'

import { executionsClient } from '../../../client'
import type { ApiError } from '../../../utils/apiErrors'
import { getErrorMessage } from '../../../utils/apiErrors'
import type { Execution } from '../execution/types'
import { useExecutionStore } from '../stores/useExecutionStore'

// ============================================================================
// Hook Options
// ============================================================================

export type UseExecutionDataOptions = {
  /**
   * Whether to fetch execution data automatically
   * @default true
   */
  enabled?: boolean

  /**
   * Whether to automatically load data into store on success
   * @default true
   */
  autoLoad?: boolean
}

// ============================================================================
// Hook Return Type
// ============================================================================

export type UseExecutionDataReturn = {
  /** Execution data from API */
  data: Execution | undefined
  /** Whether data is loading */
  isLoading: boolean
  /** Whether data fetch was successful */
  isSuccess: boolean
  /** Error if fetch failed (use parseApiError for structured errors) */
  error: ApiError | null
  /** Refetch execution data */
  refetch: () => void
}

// ============================================================================
// Hook Implementation
// ============================================================================

/**
 * Hook to fetch execution data with workflow definition and activities
 *
 * Fetches execution via REST API with includes:
 * - `workflow_definition`: For building visualization graph
 * - `activities`: For initial activity states
 *
 * By default, automatically loads the fetched data into the execution store.
 *
 * @param executionId - Execution ID to fetch
 * @param options - Hook options
 * @returns Execution data and loading state
 *
 * @example
 * ```tsx
 * function ExecutionVisualization({ executionId }: Props) {
 *   const { data, isLoading, error } = useExecutionData(executionId)
 *
 *   if (isLoading) return <SynLoadingState />
 *   if (error) return <SynErrorState error={error} />
 *
 *   return <ExecutionGraph execution={data} />
 * }
 * ```
 *
 * @example With manual loading
 * ```tsx
 * function ExecutionVisualization({ executionId }: Props) {
 *   const { data, isLoading } = useExecutionData(executionId, {
 *     autoLoad: false
 *   })
 *
 *   const handleLoad = () => {
 *     if (data) {
 *       useExecutionStore.getState().setExecution(data)
 *     }
 *   }
 *
 *   return <Button onClick={handleLoad}>Load Execution</Button>
 * }
 * ```
 */
export function useExecutionData(executionId: string, options: UseExecutionDataOptions = {}): UseExecutionDataReturn {
  const { enabled = true, autoLoad = true } = options

  // Store actions
  const setExecution = useExecutionStore((state) => state.setExecution)
  const setError = useExecutionStore((state) => state.setError)

  // Fetch execution with includes
  const query = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    {
      params: {
        path: {
          execution_id: executionId,
        },
        query: {
          include: 'workflow_definition,activities',
        },
      },
    },
    {
      enabled: enabled && !!executionId,
    }
  )

  const { data, isLoading, isSuccess, error, refetch } = query

  // Auto-load data into store on successful fetch
  useEffect(() => {
    if (autoLoad && isSuccess && data) {
      try {
        setExecution(data as Execution)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err : new Error(getErrorMessage(err)))
      }
    }
  }, [autoLoad, isSuccess, data, setExecution, setError])

  // Set error in store if fetch fails
  useEffect(() => {
    if (error) {
      setError(error instanceof Error ? error : new Error(getErrorMessage(error)))
    }
  }, [error, setError])

  return {
    data: data as Execution | undefined,
    isLoading,
    isSuccess,
    error: (error as ApiError | null) ?? null,
    refetch,
  }
}

/**
 * Hook to check if execution should use WebSocket streaming
 *
 * Completed executions should use REST data only (no WebSocket needed).
 * Running executions should connect to WebSocket for real-time updates.
 *
 * @param executionId - Execution ID to check
 * @returns Whether to use WebSocket streaming
 *
 * @example
 * ```tsx
 * function ExecutionVisualization({ executionId }: Props) {
 *   const { data } = useExecutionData(executionId)
 *   const shouldStream = useShouldStreamExecution(executionId)
 *
 *   if (shouldStream) {
 *     return <LiveExecutionView executionId={executionId} />
 *   }
 *
 *   return <CompletedExecutionView execution={data} />
 * }
 * ```
 */
export function useShouldStreamExecution(executionId: string): boolean {
  const { data, isSuccess } = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    {
      params: {
        path: {
          execution_id: executionId || '',
        },
      },
    },
    {
      enabled: !!executionId,
    }
  )

  // Don't stream if data not loaded yet
  if (!isSuccess || !data) {
    return false
  }

  const execution = data as Execution
  const terminalStatuses = ['completed', 'completed_with_errors', 'failed', 'cancelled']
  return !terminalStatuses.includes(execution.status ?? '')
}
