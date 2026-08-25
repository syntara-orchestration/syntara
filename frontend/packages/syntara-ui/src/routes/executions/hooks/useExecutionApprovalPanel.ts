import type { Approval } from '@syntara/contracts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAlerts } from '../../../providers/alerts'
import {
  canvasNodeIdFromApprovalNodeId,
  findApprovalForCanvasNode,
  findNodeByApprovalNodeId,
} from '../../approvals/approvalNodeId'
import { getApprovalPromptFromNode } from '../../approvals/approvalPrompt'
import { ACTIVITY_STATUS, isTerminalState } from '../../builder/utils/executionState/executionHelpers'
import { latestActivityStateForCanvasNode } from '../../workflows/execution/utils/activityState'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

import { useAutoApprovalDetection } from './useAutoApprovalDetection'
import type { useExecutionNodeClick } from './useExecutionNodeClick'
import { useFetchApprovalForUrlParam } from './useFetchApprovalForUrlParam'

type NodeClickResult = ReturnType<typeof useExecutionNodeClick>

export type WorkflowDefinitionLike = {
  nodes?: Array<Record<string, unknown>>
  workflow?: { activities?: Array<Record<string, unknown>> }
}

/**
 * Manages approval side panel UI state and integrations (Layer 4: UI).
 *
 * Responsibilities:
 * - Panel open/close state
 * - URL-based deep linking (`?approval=abc-123`)
 * - WebSocket-based auto-detection of new approvals
 * - Extracting approval message/prompt from workflow definition
 *
 * Part of the approval hooks architecture. See `useExecutionNodeClick.ts` for the full layering explanation.
 */
export function useExecutionApprovalPanel(
  executionId: string | undefined,
  searchParams: string,
  nodeClick: NodeClickResult,
  workflowDefinition: WorkflowDefinitionLike | undefined
) {
  const { clearApprovals, setApprovalsAndIndex, fetchApprovals, currentApproval, approvals } = nodeClick
  const [panelOpen, setPanelOpen] = useState(false)
  const prevApprovalsLengthRef = useRef(0)
  const { showError } = useAlerts()

  const approvalIdFromUrl = useMemo(() => {
    return new URLSearchParams(searchParams).get('approval')
  }, [searchParams])

  const urlApproval = useFetchApprovalForUrlParam(searchParams)
  const [handledApprovalId, setHandledApprovalId] = useState<string | null>(null)
  if (!approvalIdFromUrl && handledApprovalId !== null) {
    setHandledApprovalId(null)
  } else if (urlApproval?.id && urlApproval.id !== handledApprovalId) {
    setHandledApprovalId(urlApproval.id)
    // Fetch all approvals and find the index of the URL approval
    fetchApprovals()
      .then((fetchedApprovals) => {
        const index = fetchedApprovals.findIndex((a) => a.id === urlApproval.id)
        if (index >= 0) {
          setApprovalsAndIndex(fetchedApprovals, index)
        } else {
          // URL approval not found, default to first
          setApprovalsAndIndex(fetchedApprovals, 0)
        }
        setPanelOpen(true)
      })
      .catch(() => {
        showError({
          title: 'Failed to load approval',
          description: 'Could not fetch approval details. Please try again.',
        })
      })
  }

  const open = useCallback(() => {
    setPanelOpen(true)
  }, [])

  const close = useCallback(() => {
    setPanelOpen(false)
  }, [])

  const dismissInFlightRef = useRef(false)
  const dismiss = useCallback(() => {
    if (dismissInFlightRef.current) return
    dismissInFlightRef.current = true

    fetchApprovals()
      .then((fetchedApprovals) => {
        if (fetchedApprovals.length > 0) {
          setApprovalsAndIndex(fetchedApprovals, 0)
        } else {
          setPanelOpen(false)
          clearApprovals()
        }
      })
      .catch(() => {
        setPanelOpen(false)
        clearApprovals()
      })
      .finally(() => {
        dismissInFlightRef.current = false
      })
  }, [fetchApprovals, setApprovalsAndIndex, clearApprovals])

  const handleDetected = useCallback(
    (detected: Approval) => {
      // When auto-detection finds an approval, fetch all and set to that one
      fetchApprovals()
        .then((fetchedApprovals) => {
          const index = fetchedApprovals.findIndex((a) => a.id === detected.id)
          if (index >= 0) {
            setApprovalsAndIndex(fetchedApprovals, index)
          } else {
            setApprovalsAndIndex(fetchedApprovals, 0)
          }
          setPanelOpen(true)
        })
        .catch(() => {
          showError({
            title: 'Failed to load approval',
            description: 'Could not fetch approval details. Please try again.',
          })
        })
    },
    [fetchApprovals, setApprovalsAndIndex, showError]
  )

  useAutoApprovalDetection({
    executionId,
    fetchForNode: async (nodeId: string) => {
      const fetchedApprovals = await fetchApprovals()
      return findApprovalForCanvasNode(fetchedApprovals, nodeId) ?? null
    },
    onApprovalDetected: handleDetected,
  })

  // Auto-close panel when all approvals are resolved externally (e.g., via WebSocket)
  // Use useEffect to avoid React Compiler errors about accessing refs during render
  useEffect(() => {
    const prevLength = prevApprovalsLengthRef.current
    const currentLength = approvals.length

    // Only close if we transitioned from having approvals to having none
    if (panelOpen && prevLength > 0 && currentLength === 0) {
      // Schedule state update to avoid cascading renders
      const timer = setTimeout(() => {
        setPanelOpen(false)
        clearApprovals()
      }, 0)
      prevApprovalsLengthRef.current = currentLength
      return () => clearTimeout(timer)
    }

    // Track length changes
    prevApprovalsLengthRef.current = currentLength
  }, [panelOpen, approvals.length, clearApprovals])

  // Auto-dismiss when the current approval's activity leaves "waiting" status
  // (e.g., timed out / failed / cancelled via WebSocket update)
  useEffect(() => {
    if (!panelOpen || !currentApproval) return

    const canvasId = canvasNodeIdFromApprovalNodeId(currentApproval.approval_node_id)

    const unsubscribe = useExecutionStore.subscribe(() => {
      const activityState = latestActivityStateForCanvasNode(useExecutionStore.getState().activityStates, canvasId)
      const status = activityState?.status
      if (status && status !== ACTIVITY_STATUS.WAITING && isTerminalState(status)) {
        dismiss()
      }
    })

    return unsubscribe
  }, [panelOpen, currentApproval, dismiss])

  const approvalMessage = useMemo(() => {
    if (!currentApproval || !workflowDefinition) return undefined
    const nodes = workflowDefinition.nodes ?? workflowDefinition.workflow?.activities ?? []
    const node = findNodeByApprovalNodeId(nodes, currentApproval.approval_node_id)
    return getApprovalPromptFromNode(node)
  }, [currentApproval, workflowDefinition])

  return { panelOpen, approvalMessage, open, close, dismiss }
}
