import type { Approval } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { approvalsClient } from '../../../client'

/** Type guard to ensure approval has required fields from API response */
function isValidApproval(item: unknown): item is Approval {
  return (
    typeof item === 'object' &&
    item !== null &&
    'id' in item &&
    typeof item.id === 'string' &&
    'status' in item &&
    typeof item.status === 'string'
  )
}

type UseFetchPendingApprovalsResult = {
  /** Whether a fetch is currently in progress. */
  isLoading: boolean
  /** Fetch all pending approvals for the execution. */
  fetchApprovals: () => Promise<Approval[]>
  /** Reset loading state (e.g., when closing the review view). */
  clear: () => void
}

/**
 * Hook that lazily fetches all pending approvals for a specific execution (Layer 1: Data).
 *
 * This avoids polling — the fetch is triggered on demand when the user clicks
 * a waiting approval node on the canvas or when navigation is needed.
 *
 * Part of the approval hooks architecture. See `useExecutionStepClick.ts` for the full layering explanation.
 */
export function useFetchPendingApprovals(executionId: string): UseFetchPendingApprovalsResult {
  const [isLoading, setIsLoading] = useState(false)

  const { refetch } = approvalsClient.useQuery('get', '/approvals', {
    params: {
      query: {
        ...(executionId ? { execution_id: executionId } : {}),
        status: 'pending',
      },
    },
    enabled: false, // Only fetch on demand
  })

  const fetchApprovals = useCallback(async (): Promise<Approval[]> => {
    if (!executionId) return []
    setIsLoading(true)
    try {
      const result = await refetch()
      const resources = result.data?.resources ?? []
      return resources.filter(isValidApproval)
    } finally {
      setIsLoading(false)
    }
  }, [executionId, refetch])

  /** Cancels the loading indicator when a fetch is in-flight (e.g., on execution change or panel close). */
  const clear = useCallback(() => {
    setIsLoading(false)
  }, [])

  return { isLoading, fetchApprovals, clear }
}
