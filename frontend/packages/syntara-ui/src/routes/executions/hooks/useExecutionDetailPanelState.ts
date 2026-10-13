import type { ExecutionsAPI } from '@syntara/contracts'
import type { NavigateFn } from '@tanstack/react-router'
import { useMemo } from 'react'

import type { WorkflowDefShape } from '../../builder/useActivityNameMap'

import { useApprovalNavigation } from './useApprovalNavigation'
import { useExecutionApprovalPanel } from './useExecutionApprovalPanel'
import { useExecutionDetailInteractions } from './useExecutionDetailInteractions'
import { useExecutionFormPromptPanel } from './useExecutionFormPromptPanel'
import type { useExecutionNodeClick } from './useExecutionNodeClick'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type NodeClick = ReturnType<typeof useExecutionNodeClick>

type ExecutionWorkflow = {
  version: { workflow_definition: WorkflowDefShape | null }
}

export function useExecutionDetailPanelState({
  executionId,
  searchParams,
  execution,
  workflow,
  historyCardOpen,
  navigate,
  nodeClick,
}: Readonly<{
  executionId: string | undefined
  searchParams: string
  execution: Execution | undefined
  workflow: ExecutionWorkflow | undefined
  historyCardOpen: boolean
  navigate: NavigateFn
  nodeClick: NodeClick
}>) {
  const workflowDefinition = execution?.workflow_definition ?? undefined
  const workflowDefinitionForInteractions = workflow?.version.workflow_definition ?? undefined

  const approval = useExecutionApprovalPanel(executionId, searchParams, nodeClick, workflowDefinition)
  const formPromptPanel = useExecutionFormPromptPanel(executionId, searchParams, nodeClick, {
    workflowDefinition,
    navigate,
  })

  const approvalNavigation = useApprovalNavigation(
    nodeClick.currentIndex,
    nodeClick.navigateToIndex,
    nodeClick.approvals
  )
  const formPromptNavigation = useApprovalNavigation(
    nodeClick.formPromptIndex,
    nodeClick.navigateToFormPromptIndex,
    nodeClick.formPrompts
  )

  const interactions = useExecutionDetailInteractions({
    executionId: executionId ?? '',
    historyCardOpen,
    navigate,
    nodeClick,
    approval,
    formPromptPanel,
    workflowDefinition: workflowDefinitionForInteractions,
  })

  const hasOpenExecutionSidePanel = useMemo(
    () =>
      Boolean(
        (formPromptPanel.panelOpen && nodeClick.currentFormPrompt) || (approval.panelOpen && nodeClick.currentApproval)
      ),
    [formPromptPanel.panelOpen, nodeClick.currentFormPrompt, approval.panelOpen, nodeClick.currentApproval]
  )

  return {
    approval,
    formPromptPanel,
    approvalNavigation,
    formPromptNavigation,
    workflowDefinitionForSidePanel: workflowDefinitionForInteractions,
    hasOpenExecutionSidePanel,
    ...interactions,
  }
}
