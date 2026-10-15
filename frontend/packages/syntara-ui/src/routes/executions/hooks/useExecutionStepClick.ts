import { useCallback, useRef, useState } from 'react'

import { isWaitingApprovalNode, useExecutionApprovals } from './useExecutionApprovals'

/**
 * Execution Approval Hooks Architecture
 *
 * The approval system uses a layered hook composition pattern for separation of concerns:
 *
 * **Layer 1: Data (useFetchPendingApprovals)**
 * - Fetches approval list from API on demand
 * - Returns: `approvals[]`, `fetchApprovals()`, `isLoading`
 * - Single responsibility: API interaction
 *
 * **Layer 2: State (useExecutionApprovals)**
 * - Manages approval navigation state (current index, current approval)
 * - Handles approval list updates and index clamping
 * - Provides handlers for node clicks on waiting approval steps
 * - Delegates to: `useFetchPendingApprovals`
 *
 * **Layer 3: Interaction (useExecutionStepClick)** ← You are here
 * - Composes approval clicks + step selection clicks
 * - Routes waiting approval steps → approval flow
 * - Routes completed/failed nodes → details panel
 * - Delegates to: `useExecutionApprovals`
 *
 * **Layer 4: UI (useExecutionApprovalPanel)**
 * - Manages panel open/close state
 * - Handles URL-based deep linking (`?approval=abc-123`)
 * - Integrates auto-detection via WebSocket
 * - Delegates to: result from `useExecutionStepClick`
 *
 * **Usage in ExecutionDetail:**
 * ```tsx
 * const stepClick = useExecutionStepClick(executionId)
 * const approval = useExecutionApprovalPanel(executionId, searchParams, stepClick, workflowDef)
 * ```
 *
 * **Why layered instead of one big hook?**
 * - Each layer has a single, testable responsibility
 * - `useExecutionStepClick` can be used independently for non-approval step clicks
 * - `useFetchPendingApprovals` is reusable in other contexts (e.g., approval list page)
 * - Easier to test in isolation (4 focused test files vs 1 massive test file)
 * - Follows React hook composition patterns (like `useState` + `useEffect` instead of one giant state hook)
 */

type ExecutionNode = { id: string; type?: string; data: Record<string, unknown> }

type ExecutionState = {
  status?: string
}

function getExecutionState(node: ExecutionNode): ExecutionState | undefined {
  const value = node.data.__executionState
  if (typeof value === 'object' && value !== null) return value
  return undefined
}

function getStepDisplayName(node: ExecutionNode): string {
  const name = node.data.name
  return typeof name === 'string' ? name : node.id
}

function getStepActivityId(node: ExecutionNode): string {
  const defId = node.data.definitionId
  if (typeof defId === 'string') return defId
  return node.id
}

/**
 * Composes node click handling for the execution view (Layer 3: Interaction).
 *
 * Routes canvas node clicks to either:
 * 1. Approval nodes in "waiting" status → delegates to useExecutionApprovals
 * 2. Completed/failed steps → toggles step details panel via selectedStepId
 *
 * See file-level JSDoc for the full approval hooks architecture.
 */
export function useExecutionStepClick(executionId: string | undefined) {
  const {
    approvals,
    currentIndex,
    currentApproval,
    isLoading: isApprovalLoading,
    handleNodeClick: handleApprovalNodeClick,
    navigateToIndex,
    clearApprovals,
    setApprovalsAndIndex,
    fetchApprovals,
  } = useExecutionApprovals(executionId)

  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [selectedStepName, setSelectedStepName] = useState<string | null>(null)
  // Ref mirrors selectedStepId so the click callback never goes stale
  const selectedStepIdRef = useRef<string | null>(null)

  const handleNodeClick = useCallback(
    (event: React.MouseEvent, node: ExecutionNode) => {
      if (isWaitingApprovalNode(node)) {
        handleApprovalNodeClick(event, node)
        return
      }

      const execState = getExecutionState(node)
      if (execState?.status === 'completed' || execState?.status === 'failed') {
        const activityId = getStepActivityId(node)
        selectedStepIdRef.current = activityId
        setSelectedStepId(activityId)
        setSelectedStepName(getStepDisplayName(node))
      }
    },
    [handleApprovalNodeClick]
  )

  const selectStep = useCallback((stepId: string, stepName: string) => {
    selectedStepIdRef.current = stepId
    setSelectedStepId(stepId)
    setSelectedStepName(stepName)
  }, [])

  const deselectStep = useCallback(() => {
    selectedStepIdRef.current = null
    setSelectedStepId(null)
    setSelectedStepName(null)
  }, [])

  return {
    // Approval state (multi-approval support)
    approvals,
    currentIndex,
    currentApproval,
    isApprovalLoading,
    navigateToIndex,
    clearApprovals,
    setApprovalsAndIndex,
    fetchApprovals,
    // Step selection state
    selectedStepId,
    selectedStepName,
    selectStep,
    deselectStep,
    handleNodeClick,
  }
}
