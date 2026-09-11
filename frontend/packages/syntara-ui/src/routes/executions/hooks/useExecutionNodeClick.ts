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
 * - Provides handlers for node clicks on waiting approval nodes
 * - Delegates to: `useFetchPendingApprovals`
 *
 * **Layer 3: Interaction (useExecutionNodeClick)** ← You are here
 * - Composes approval clicks + node selection clicks
 * - Routes waiting approval nodes → approval flow
 * - Routes completed/failed nodes → details panel
 * - Delegates to: `useExecutionApprovals`
 *
 * **Layer 4: UI (useExecutionApprovalPanel)**
 * - Manages panel open/close state
 * - Handles URL-based deep linking (`?approval=abc-123`)
 * - Integrates auto-detection via WebSocket
 * - Delegates to: result from `useExecutionNodeClick`
 *
 * **Usage in ExecutionDetail:**
 * ```tsx
 * const nodeClick = useExecutionNodeClick(executionId)
 * const approval = useExecutionApprovalPanel(executionId, searchParams, nodeClick, workflowDef)
 * ```
 *
 * **Why layered instead of one big hook?**
 * - Each layer has a single, testable responsibility
 * - `useExecutionNodeClick` can be used independently for non-approval node clicks
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

function getNodeDisplayName(node: ExecutionNode): string {
  const name = node.data.name
  return typeof name === 'string' ? name : node.id
}

function getNodeActivityId(node: ExecutionNode): string {
  const defId = node.data.definitionId
  if (typeof defId === 'string') return defId
  return node.id
}

/**
 * Composes node click handling for the execution view (Layer 3: Interaction).
 *
 * Routes canvas node clicks to either:
 * 1. Approval nodes in "waiting" status → delegates to useExecutionApprovals
 * 2. Completed/failed nodes → toggles node details panel via selectedNodeId
 *
 * See file-level JSDoc for the full approval hooks architecture.
 */
export function useExecutionNodeClick(executionId: string | undefined) {
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

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNodeName, setSelectedNodeName] = useState<string | null>(null)
  // Ref mirrors selectedNodeId so the click callback never goes stale
  const selectedNodeIdRef = useRef<string | null>(null)

  const handleNodeClick = useCallback(
    (event: React.MouseEvent, node: ExecutionNode) => {
      if (isWaitingApprovalNode(node)) {
        handleApprovalNodeClick(event, node)
        return
      }

      const execState = getExecutionState(node)
      if (execState?.status === 'completed' || execState?.status === 'failed') {
        const activityId = getNodeActivityId(node)
        selectedNodeIdRef.current = activityId
        setSelectedNodeId(activityId)
        setSelectedNodeName(getNodeDisplayName(node))
      }
    },
    [handleApprovalNodeClick]
  )

  const selectNode = useCallback((nodeId: string, nodeName: string) => {
    selectedNodeIdRef.current = nodeId
    setSelectedNodeId(nodeId)
    setSelectedNodeName(nodeName)
  }, [])

  const deselectNode = useCallback(() => {
    selectedNodeIdRef.current = null
    setSelectedNodeId(null)
    setSelectedNodeName(null)
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
    // Node selection state
    selectedNodeId,
    selectedNodeName,
    selectNode,
    deselectNode,
    handleNodeClick,
  }
}
