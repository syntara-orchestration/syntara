import type { Approval } from '@syntara/contracts'

import { useAutoWaitingNodeDetection } from './useAutoWaitingNodeDetection'

type UseAutoApprovalDetectionOptions = {
  executionId: string | undefined
  shouldDetectNode?: (nodeId: string) => boolean
  fetchForNode: (approvalNodeId: string) => Promise<Approval | null>
  onApprovalDetected: (approval: Approval) => void
}

/** Auto-open approval panel when a waiting approval node appears on the canvas. */
export function useAutoApprovalDetection(options: UseAutoApprovalDetectionOptions): void {
  useAutoWaitingNodeDetection({
    executionId: options.executionId,
    shouldDetectNode: options.shouldDetectNode,
    fetchForNode: options.fetchForNode,
    onDetected: options.onApprovalDetected,
  })
}
