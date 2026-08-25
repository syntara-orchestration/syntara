import { ActivityTypeEnum, type Approval } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import { useCallback, useMemo, useState } from 'react'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { findNodeByApprovalNodeId } from '../../approvals/approvalNodeId'
import { getApprovalPromptFromNode, getApprovalPromptFromRecord } from '../../approvals/approvalPrompt'
import { useAutoApprovalDetection } from '../../executions/hooks/useAutoApprovalDetection'
import {
  type ExecutionNode,
  isWaitingApprovalNode,
  useExecutionApproval,
} from '../../executions/hooks/useExecutionApproval'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { EXECUTION_BADGE_SELECTOR } from '../components/ExecutionStatusBadge'

type UseBuilderApprovalParams = {
  mostRecentExecutionId: string | null | undefined
  showMostRecentRunPanelInEditor: boolean
  currentWorkflow: WorkflowDefinition | null
  handleNodeClick: (event: React.MouseEvent, node: Node<NodeType['data']>) => void
  isLiveRunActive: boolean
}

type UseBuilderApprovalResult = {
  pendingApproval: Approval | null
  isApprovalLoading: boolean
  approvalViewOpen: boolean
  activityNameMap: Map<string, string>
  /** Persisted approval prompt, falling back to the node's Message field. */
  approvalMessage: string | undefined
  wrappedHandleNodeClick: (event: React.MouseEvent, node: Node<NodeType['data']>) => void
  handleApprovalClose: () => void
  handleApprovalDismiss: () => void
  openApprovalView: () => void
}

export function useBuilderApproval({
  mostRecentExecutionId,
  showMostRecentRunPanelInEditor,
  currentWorkflow,
  handleNodeClick,
  isLiveRunActive,
}: UseBuilderApprovalParams): UseBuilderApprovalResult {
  const {
    pendingApproval,
    isLoading: isApprovalLoading,
    handleNodeClick: handleApprovalNodeClick,
    clearPendingApproval,
    setPendingApproval,
    fetchForNode,
  } = useExecutionApproval(mostRecentExecutionId ?? undefined)

  const [approvalViewOpen, setApprovalViewOpen] = useState(false)

  const handleApprovalClose = useCallback(() => {
    setApprovalViewOpen(false)
  }, [])

  const handleApprovalDismiss = useCallback(() => {
    setApprovalViewOpen(false)
    clearPendingApproval()
  }, [clearPendingApproval])

  const openApprovalView = useCallback(() => {
    setApprovalViewOpen(true)
  }, [])

  const handleApprovalDetected = useCallback(
    (approval: Approval) => {
      setPendingApproval(approval)
      setApprovalViewOpen(true)
    },
    [setPendingApproval]
  )

  useAutoApprovalDetection({
    executionId: isLiveRunActive ? (mostRecentExecutionId ?? undefined) : undefined,
    fetchForNode,
    onApprovalDetected: handleApprovalDetected,
  })

  const activityNameMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const activity of currentWorkflow?.workflow?.activities ?? []) {
      if (activity.id && activity.name) {
        map.set(activity.id, activity.name)
      }
    }
    return map
  }, [currentWorkflow])

  const approvalMessage = useMemo(() => {
    if (!pendingApproval) return undefined
    const fromRecord = getApprovalPromptFromRecord(pendingApproval)
    if (fromRecord) return fromRecord
    if (!currentWorkflow) return undefined
    const activities = currentWorkflow.workflow?.activities ?? []
    const activity = findNodeByApprovalNodeId(activities, pendingApproval.approval_node_id)
    if (activity?.type !== ActivityTypeEnum.APPROVAL) return undefined
    return getApprovalPromptFromNode(activity)
  }, [pendingApproval, currentWorkflow])

  const wrappedHandleNodeClick = useCallback(
    (event: React.MouseEvent, node: Node<NodeType['data']>) => {
      if (showMostRecentRunPanelInEditor) {
        const target = event.target as HTMLElement | null
        const clickedBadge = target?.closest?.(EXECUTION_BADGE_SELECTOR) != null
        const execNode: ExecutionNode = { id: node.id, type: node.type, data: node.data as Record<string, unknown> }
        if (clickedBadge && isWaitingApprovalNode(execNode)) {
          handleApprovalNodeClick(event, execNode)
          setApprovalViewOpen(true)
          return
        }
      }
      if (!isLiveRunActive) {
        handleNodeClick(event, node)
      }
    },
    [showMostRecentRunPanelInEditor, handleApprovalNodeClick, handleNodeClick, isLiveRunActive]
  )

  return {
    pendingApproval,
    isApprovalLoading,
    approvalViewOpen,
    activityNameMap,
    approvalMessage,
    wrappedHandleNodeClick,
    handleApprovalClose,
    handleApprovalDismiss,
    openApprovalView,
  }
}
