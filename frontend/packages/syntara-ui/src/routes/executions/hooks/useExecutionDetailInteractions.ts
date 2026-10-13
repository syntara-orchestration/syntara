import type { NavigateFn } from '@tanstack/react-router'
import type React from 'react'
import { useCallback } from 'react'

import { FlowNodeType } from '../../../constants'
import { detachPromise } from '../../../utils/detachPromise'
import type { WorkflowDefShape } from '../../builder/useActivityNameMap'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'
import { isFormPromptActivityWaiting } from '../formPrompt/formPromptActivityState'
import { resolveCanvasNodeType } from '../formPrompt/resolveCanvasNodeType'

import type { useExecutionApprovalPanel } from './useExecutionApprovalPanel'
import { isWaitingApprovalNode } from './useExecutionApprovals'
import type { useExecutionFormPromptPanel } from './useExecutionFormPromptPanel'
import { isFormPromptNode, isWaitingFormPromptNode } from './useExecutionFormPrompts'
import type { useExecutionNodeClick } from './useExecutionNodeClick'

type NodeClick = ReturnType<typeof useExecutionNodeClick>
type ApprovalPanel = ReturnType<typeof useExecutionApprovalPanel>
type FormPromptPanel = ReturnType<typeof useExecutionFormPromptPanel>

export function useExecutionDetailInteractions({
  executionId,
  historyCardOpen,
  navigate,
  nodeClick,
  approval,
  formPromptPanel,
  workflowDefinition,
}: Readonly<{
  executionId: string
  historyCardOpen: boolean
  navigate: NavigateFn
  nodeClick: NodeClick
  approval: ApprovalPanel
  formPromptPanel: FormPromptPanel
  workflowDefinition?: WorkflowDefShape
}>) {
  const { handleNodeClick, selectNode, handleActivityRowClick } = nodeClick

  const onCanvasNodeClick = useCallback(
    (event: React.MouseEvent, node: Parameters<typeof handleNodeClick>[1]) => {
      handleNodeClick(event, node)
      if (isWaitingFormPromptNode(node)) {
        formPromptPanel.open()
        approval.close()
      } else if (isFormPromptNode(node)) {
        formPromptPanel.close()
      } else if (isWaitingApprovalNode(node)) {
        approval.open()
        formPromptPanel.close()
      }
    },
    [handleNodeClick, formPromptPanel, approval]
  )

  const onActivityRowSelect = useCallback(
    (nodeId: string, nodeName: string, activityKey?: string) => {
      selectNode(nodeId, nodeName)
      const lookupKey = activityKey ?? nodeId
      if (resolveCanvasNodeType(lookupKey, workflowDefinition) === FlowNodeType.FORM_PROMPT) {
        const activityStates = useExecutionStore.getState().activityStates
        if (isFormPromptActivityWaiting(lookupKey, activityStates)) {
          handleActivityRowClick(lookupKey)
          formPromptPanel.open()
          approval.close()
        } else {
          formPromptPanel.close()
        }
        return
      }
      formPromptPanel.close()
    },
    [formPromptPanel, selectNode, handleActivityRowClick, workflowDefinition, approval]
  )

  const toggleHistoryCard = useCallback(() => {
    const willOpen = !historyCardOpen
    if (willOpen) {
      approval.close()
      formPromptPanel.close()
    }
    detachPromise(
      navigate({
        to: '/executions/$executionId',
        params: { executionId },
        search: (prev: Record<string, unknown>) => ({ ...prev, history: willOpen ? 'open' : 'closed' }),
      })
    )
  }, [approval, executionId, formPromptPanel, historyCardOpen, navigate])

  return { onCanvasNodeClick, onActivityRowSelect, toggleHistoryCard }
}
