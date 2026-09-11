import type { Approval } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'

import { FlowNodeType } from '../../../constants'
import { detachPromise } from '../../../utils/detachPromise'
import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'

import { useFetchApprovalForNode } from './useFetchApprovalForNode'

export type ExecutionNode = { id: string; type?: string; data: Record<string, unknown> }

/** Returns true if the node is an approval node with activity status "waiting". */
export function isWaitingApprovalNode(node: ExecutionNode): boolean {
  if (node.type !== FlowNodeType.APPROVAL) return false
  const executionState = node.data.__executionState as { status?: string } | undefined
  return executionState?.status === ACTIVITY_STATUS.WAITING
}

type UseExecutionApprovalResult = {
  /** The pending approval for the selected node, or null. */
  pendingApproval: Approval | null
  /** Whether an approval fetch is in progress. */
  isLoading: boolean
  /** Handler for node clicks on the execution canvas. Only responds to approval nodes in "waiting" status. */
  handleNodeClick: (event: React.MouseEvent, node: ExecutionNode) => void
  /** Clear the pending approval (e.g., after a decision is submitted). */
  clearPendingApproval: () => void
  /** Set the pending approval directly (used by auto-detection). */
  setPendingApproval: (approval: Approval | null) => void
  /** Fetch the approval for a specific node ID. */
  fetchForNode: (approvalNodeId: string) => Promise<Approval | null>
}

/**
 * Manages approval detection and selection in the execution view.
 * When the user clicks an approval node in "waiting" status on the canvas,
 * this hook fetches the corresponding pending approval from the API.
 */
export function useExecutionApproval(executionId: string | undefined): UseExecutionApprovalResult {
  const [pendingApproval, setPendingApproval] = useState<Approval | null>(null)
  const { fetchForNode, clear, isLoading } = useFetchApprovalForNode(executionId ?? '')
  const executionIdRef = useRef(executionId)
  const latestNodeIdRef = useRef<string | null>(null)

  // Clear approval state and sync ref when execution changes
  useEffect(() => {
    executionIdRef.current = executionId
    latestNodeIdRef.current = null
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear approval UI when the route execution id changes
    setPendingApproval(null)
    clear()
  }, [executionId, clear])

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: ExecutionNode) => {
      if (!isWaitingApprovalNode(node)) return
      if (latestNodeIdRef.current === node.id && pendingApproval) return

      latestNodeIdRef.current = node.id
      const capturedExecutionId = executionIdRef.current
      detachPromise(
        fetchForNode(node.id)
          .then((approval) => {
            if (approval && executionIdRef.current === capturedExecutionId && latestNodeIdRef.current === node.id) {
              setPendingApproval(approval)
            }
          })
          .catch(() => {
            // Fetch failed — user can retry by clicking the node again
          })
      )
    },
    [fetchForNode, pendingApproval]
  )

  const clearPendingApproval = useCallback(() => {
    setPendingApproval(null)
    latestNodeIdRef.current = null
    clear()
  }, [clear])

  return { pendingApproval, isLoading, handleNodeClick, clearPendingApproval, setPendingApproval, fetchForNode }
}
