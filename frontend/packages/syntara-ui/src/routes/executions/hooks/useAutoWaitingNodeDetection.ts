import { useCallback, useEffect, useRef } from 'react'

import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

const MAX_FETCH_ATTEMPTS = 5
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 16000]

type UseAutoWaitingNodeDetectionOptions<T> = {
  executionId: string | undefined
  /** When set, only waiting nodes passing this check trigger a fetch. */
  shouldDetectNode?: (nodeId: string) => boolean
  fetchForNode: (nodeId: string) => Promise<T | null>
  onDetected: (item: T) => void
  onFetchError?: (nodeId: string, error: unknown) => void
}

/**
 * Watches the execution store for activities entering "waiting" status and
 * fetches human-task metadata for the first matching node.
 */
export function useAutoWaitingNodeDetection<T>({
  executionId,
  shouldDetectNode,
  fetchForNode,
  onDetected,
  onFetchError,
}: UseAutoWaitingNodeDetectionOptions<T>): void {
  const detectedNodeIds = useRef(new Set<string>())
  const fetchingRef = useRef(false)
  const inFlightNodeId = useRef<string | null>(null)
  const failureAttempts = useRef(new Map<string, number>())
  const retryAfterMs = useRef(new Map<string, number>())
  const generationRef = useRef(0)
  const scanRef = useRef<() => void>(() => {})

  useEffect(() => {
    generationRef.current += 1
    detectedNodeIds.current = new Set<string>()
    fetchingRef.current = false
    inFlightNodeId.current = null
    failureAttempts.current = new Map()
    retryAfterMs.current = new Map()
  }, [executionId])

  const scheduleRetry = useCallback((nodeId: string, generation: number) => {
    const attempt = (failureAttempts.current.get(nodeId) ?? 0) + 1
    failureAttempts.current.set(nodeId, attempt)
    if (attempt >= MAX_FETCH_ATTEMPTS) {
      return
    }
    const delayIndex = Math.min(attempt - 1, RETRY_DELAYS_MS.length - 1)
    const delay = RETRY_DELAYS_MS[delayIndex] ?? RETRY_DELAYS_MS.at(-1) ?? 16000
    retryAfterMs.current.set(nodeId, Date.now() + delay)
    window.setTimeout(() => {
      if (generation === generationRef.current) {
        scanRef.current()
      }
    }, delay)
  }, [])

  const checkAndFetch = useCallback(() => {
    if (!executionId || fetchingRef.current) return

    const activityStates = useExecutionStore.getState().activityStates
    const now = Date.now()

    for (const [nodeId, state] of activityStates) {
      if (state?.status !== ACTIVITY_STATUS.WAITING) {
        detectedNodeIds.current.delete(nodeId)
        failureAttempts.current.delete(nodeId)
        retryAfterMs.current.delete(nodeId)
        continue
      }

      if (detectedNodeIds.current.has(nodeId)) continue

      const retryAfter = retryAfterMs.current.get(nodeId)
      if (retryAfter !== undefined && now < retryAfter) continue

      const attempts = failureAttempts.current.get(nodeId) ?? 0
      if (attempts >= MAX_FETCH_ATTEMPTS) continue

      if (shouldDetectNode && !shouldDetectNode(nodeId)) continue

      fetchingRef.current = true
      inFlightNodeId.current = nodeId
      const generation = generationRef.current

      fetchForNode(nodeId)
        .then((item) => {
          if (generation !== generationRef.current) return
          if (item) {
            detectedNodeIds.current.add(nodeId)
            failureAttempts.current.delete(nodeId)
            retryAfterMs.current.delete(nodeId)
            onDetected(item)
          } else {
            scheduleRetry(nodeId, generation)
          }
        })
        .catch((error: unknown) => {
          if (generation !== generationRef.current) return
          onFetchError?.(nodeId, error)
          scheduleRetry(nodeId, generation)
        })
        .finally(() => {
          if (generation === generationRef.current) {
            fetchingRef.current = false
            inFlightNodeId.current = null
            scanRef.current()
          }
        })
      break
    }
  }, [executionId, shouldDetectNode, fetchForNode, onDetected, onFetchError, scheduleRetry])

  useEffect(() => {
    scanRef.current = checkAndFetch
  }, [checkAndFetch])

  useEffect(() => {
    const unsubscribe = useExecutionStore.subscribe(checkAndFetch)
    checkAndFetch()
    return unsubscribe
  }, [checkAndFetch])
}
