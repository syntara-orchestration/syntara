import type { Approval } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { approvalsClient } from '../../../client'
import { findApprovalForCanvasNode } from '../../approvals/approvalNodeId'

type UseFetchApprovalForStepResult = {
  /** Whether a fetch is currently in progress. */
  isLoading: boolean
  /** Fetch the pending approval for the given step. Returns the approval if found. */
  fetchForStep: (approvalNodeId: string) => Promise<Approval | null>
  /** Reset loading state (e.g., when closing the review view). */
  clear: () => void
}

/**
 * Hook that lazily fetches pending approvals for a specific execution,
 * then filters client-side by approval_node_id to find the matching approval.
 *
 * This avoids polling — the fetch is triggered on demand when the user clicks
 * a waiting approval step on the canvas.
 */
export function useFetchApprovalForStep(executionId: string): UseFetchApprovalForStepResult {
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

  const fetchForStep = useCallback(
    async (approvalNodeId: string): Promise<Approval | null> => {
      if (!executionId) return null
      setIsLoading(true)
      try {
        const result = await refetch()
        const approvals = result.data?.resources ?? []
        const match = findApprovalForCanvasNode(approvals, approvalNodeId)
        const resolved = (match?.id ? match : null) as Approval | null
        return resolved
      } finally {
        setIsLoading(false)
      }
    },
    [executionId, refetch]
  )

  const clear = useCallback(() => {
    setIsLoading(false)
  }, [])

  return { isLoading, fetchForStep, clear }
}
