import type { Approval } from '@syntara/contracts'
import { useCallback, useEffect, useRef } from 'react'

import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

type UseAutoApprovalDetectionOptions = {
  executionId: string | undefined
  fetchForStep: (approvalNodeId: string) => Promise<Approval | null>
  onApprovalDetected: (approval: Approval) => void
  /**
   * WAITING is used by human-in-the-loop steps (e.g. approvals and form prompts).
   * Callers that only care about approvals should pass a predicate that limits
   * which canvas node IDs trigger `fetchForStep`.
   */
  shouldProbeWaitingNode?: (canvasNodeId: string) => boolean
}

/**
 * Watches the execution store for any activity entering "waiting" status and
 * runs `fetchForStep` for the first matching node.
 *
 * WAITING is not approval-exclusive — use `shouldProbeWaitingNode` when the
 * fetch only applies to approval steps (e.g. in the workflow builder).
 */
export function useAutoApprovalDetection({
  executionId,
  fetchForStep,
  onApprovalDetected,
  shouldProbeWaitingNode,
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

      if (shouldProbeWaitingNode && !shouldProbeWaitingNode(nodeId)) {
        continue
      }

      if (detectedNodeIds.current.has(nodeId)) continue

      detectedNodeIds.current.add(nodeId)
      fetchingRef.current = true
      const generation = generationRef.current

      fetchForStep(nodeId)
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
  }, [executionId, fetchForStep, onApprovalDetected, shouldProbeWaitingNode])

  useEffect(() => {
    scanRef.current = checkAndFetch
  }, [checkAndFetch])

  useEffect(() => {
    const unsubscribe = useExecutionStore.subscribe(checkAndFetch)
    checkAndFetch()
    return unsubscribe
  }, [checkAndFetch])
}
