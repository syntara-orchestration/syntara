import type { Approval } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'

import { FlowNodeType } from '../../../constants'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { findApprovalIndexForCanvasNode } from '../../approvals/approvalNodeId'
import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'

import { useFetchPendingApprovals } from './useFetchPendingApprovals'

export type ExecutionNode = { id: string; type?: string; data: Record<string, unknown> }

/** Returns true if the node is an approval node with activity status "waiting". */
export function isWaitingApprovalNode(node: ExecutionNode): boolean {
  if (node.type !== FlowNodeType.APPROVAL) return false
  const executionState = node.data.__executionState
  if (!executionState || typeof executionState !== 'object') return false
  const status = 'status' in executionState ? executionState.status : undefined
  return status === ACTIVITY_STATUS.WAITING
}

type UseExecutionApprovalsResult = {
  /** All pending approvals for the execution. */
  approvals: Approval[]
  /** The current approval index (0-based). */
  currentIndex: number
  /** The currently selected approval, or null if no approvals exist. */
  currentApproval: Approval | null
  /** Whether an approval fetch is in progress. */
  isLoading: boolean
  /** Handler for node clicks on the execution canvas. Only responds to approval nodes in "waiting" status. */
  handleNodeClick: (event: React.MouseEvent, node: ExecutionNode) => void
  /** Navigate to a specific approval by index. */
  navigateToIndex: (index: number) => void
  /** Clear the approval state (e.g., after a decision is submitted). */
  clearApprovals: () => void
  /** Set approvals and index directly (used by auto-detection and URL params). */
  setApprovalsAndIndex: (approvals: Approval[], index: number) => void
  /** Fetch all pending approvals for the execution. */
  fetchApprovals: () => Promise<Approval[]>
}

/**
 * Manages approval detection, selection, and navigation in the execution view (Layer 2: State).
 *
 * When the user clicks an approval node in "waiting" status on the canvas,
 * this hook fetches all pending approvals and sets the index to the clicked approval.
 *
 * Part of the approval hooks architecture. See `useExecutionNodeClick.ts` for the full layering explanation.
 */
export function useExecutionApprovals(executionId: string | undefined): UseExecutionApprovalsResult {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const { fetchApprovals: fetchApprovalsFromApi, clear, isLoading } = useFetchPendingApprovals(executionId ?? '')
  const { showInfo, showError } = useAlerts()
  const executionIdRef = useRef(executionId)
  const latestNodeIdRef = useRef<string | null>(null)
  const lastFetchErrorKeyRef = useRef<string | null>(null)
  const [trackedExecutionId, setTrackedExecutionId] = useState(executionId)

  // Derived current approval
  const currentApproval = approvals[currentIndex] ?? null

  // Reset state when executionId changes (during render, not in effect)
  if (trackedExecutionId !== executionId) {
    setTrackedExecutionId(executionId)
    setApprovals([])
    setCurrentIndex(0)
  }

  // Update refs in effect to avoid React Compiler error
  useEffect(() => {
    if (executionIdRef.current !== executionId) {
      latestNodeIdRef.current = null
      lastFetchErrorKeyRef.current = null
    }
    executionIdRef.current = executionId
  }, [executionId])

  // Clear fetched data when execution changes
  useEffect(() => {
    clear()
  }, [executionId, clear])

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: ExecutionNode) => {
      if (!isWaitingApprovalNode(node)) return

      latestNodeIdRef.current = node.id
      const capturedExecutionId = executionIdRef.current

      detachPromise(
        fetchApprovalsFromApi()
          .then((fetchedApprovals) => {
            if (executionIdRef.current !== capturedExecutionId || latestNodeIdRef.current !== node.id) return
            lastFetchErrorKeyRef.current = null

            const index = findApprovalIndexForCanvasNode(fetchedApprovals, node.id)
            if (index >= 0) {
              setApprovals(fetchedApprovals)
              setCurrentIndex(index)
            } else {
              // Approval was resolved or is no longer pending - provide user feedback
              showInfo({
                title: 'Approval no longer pending',
                description: 'This approval has been resolved or is no longer available.',
              })
            }
          })
          .catch((error: unknown) => {
            if (executionIdRef.current !== capturedExecutionId || latestNodeIdRef.current !== node.id) return
            const message = getErrorMessage(error)
            const key = `${node.id}::Failed to load approval::${message}`
            if (lastFetchErrorKeyRef.current === key) return
            lastFetchErrorKeyRef.current = key
            showError({
              title: 'Failed to load approval',
              description: message,
            })
          })
      )
    },
    [fetchApprovalsFromApi, showInfo, showError]
  )

  const navigateToIndex = useCallback(
    (index: number) => {
      // If approvals array is empty, reset to initial state
      // This can happen if all approvals are resolved externally (e.g., via WebSocket)
      if (approvals.length === 0) {
        setCurrentIndex(0)
        return
      }
      // Bounds check: clamp to [0, length - 1]
      const clampedIndex = Math.max(0, Math.min(index, approvals.length - 1))
      setCurrentIndex(clampedIndex)
    },
    [approvals.length]
  )

  const clearApprovals = useCallback(() => {
    setApprovals([])
    setCurrentIndex(0)
    latestNodeIdRef.current = null
    clear()
  }, [clear])

  const setApprovalsAndIndex = useCallback((newApprovals: Approval[], index: number) => {
    setApprovals(newApprovals)
    const clampedIndex = Math.max(0, Math.min(index, newApprovals.length - 1))
    setCurrentIndex(clampedIndex)
  }, [])

  const fetchApprovals = useCallback(async (): Promise<Approval[]> => {
    const fetchedApprovals = await fetchApprovalsFromApi()
    setApprovals(fetchedApprovals)
    return fetchedApprovals
  }, [fetchApprovalsFromApi])

  return {
    approvals,
    currentIndex,
    currentApproval,
    isLoading,
    handleNodeClick,
    navigateToIndex,
    clearApprovals,
    setApprovalsAndIndex,
    fetchApprovals,
  }
}
