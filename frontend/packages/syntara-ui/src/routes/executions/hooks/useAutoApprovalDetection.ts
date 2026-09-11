import type { Approval } from '@syntara/contracts'
import { useCallback, useEffect, useRef } from 'react'

import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

type UseAutoApprovalDetectionOptions = {
  executionId: string | undefined
  fetchForNode: (approvalNodeId: string) => Promise<Approval | null>
  onApprovalDetected: (approval: Approval) => void
}

/**
 * Watches the execution store for any activity entering "waiting" status.
 * The "waiting" status is exclusively used by approval nodes, so any node
 * that enters this state triggers an approval fetch.
 *
 * This enables auto-show behavior: when a live execution reaches an approval
 * node, the approval review panel opens automatically.
 */
export function useAutoApprovalDetection({
  executionId,
  fetchForNode,
  onApprovalDetected,
}: UseAutoApprovalDetectionOptions): void {
  const detectedNodeIds = useRef(new Set<string>())
  const fetchingRef = useRef(false)
  const generationRef = useRef(0)
  const scanRef = useRef<() => void>(() => {})

  useEffect(() => {
    generationRef.current += 1
    detectedNodeIds.current = new Set<string>()
    fetchingRef.current = false
  }, [executionId])

  const checkAndFetch = useCallback(() => {
    if (!executionId || fetchingRef.current) return

    const activityStates = useExecutionStore.getState().activityStates

    for (const [nodeId, state] of activityStates) {
      if (state?.status !== ACTIVITY_STATUS.WAITING) {
        detectedNodeIds.current.delete(nodeId)
        continue
      }

      if (detectedNodeIds.current.has(nodeId)) continue

      detectedNodeIds.current.add(nodeId)
      fetchingRef.current = true
      const generation = generationRef.current

      fetchForNode(nodeId)
        .then((approval) => {
          if (generation !== generationRef.current) return
          if (approval) {
            onApprovalDetected(approval)
          }
        })
        .catch(() => {
          if (generation === generationRef.current) {
            detectedNodeIds.current.delete(nodeId)
          }
        })
        .finally(() => {
          if (generation === generationRef.current) {
            fetchingRef.current = false
            scanRef.current()
          }
        })
      break
    }
  }, [executionId, fetchForNode, onApprovalDetected])

  useEffect(() => {
    scanRef.current = checkAndFetch
  }, [checkAndFetch])

  useEffect(() => {
    const unsubscribe = useExecutionStore.subscribe(checkAndFetch)
    checkAndFetch()
    return unsubscribe
  }, [checkAndFetch])
}
