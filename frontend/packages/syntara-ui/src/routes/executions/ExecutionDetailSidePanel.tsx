import type { Approval, FormsAPI } from '@syntara/contracts'

import { ApprovalSidePanel } from './ApprovalSidePanel'
import type { WorkflowDefinitionLike } from './formPrompt/resolveCanvasNodeType'
import { FormPromptSidePanel } from './FormPromptSidePanel'
import type { useApprovalNavigation } from './hooks/useApprovalNavigation'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

type ApprovalNavigation = ReturnType<typeof useApprovalNavigation>

type ExecutionDetailSidePanelProps = Readonly<{
  formPromptPanelOpen: boolean
  currentFormPrompt: FormPromptSummary | null
  formPromptNavigation: ApprovalNavigation
  formPromptIndex: number
  formPromptCount: number
  executionId: string
  activityNameMap: Map<string, string>
  onFormPromptClose: () => void
  onFormPromptSubmitted: () => void
  workflowDefinition?: WorkflowDefinitionLike
  approvalPanelOpen: boolean
  currentApproval: Approval | null | undefined
  approvalMessage: string | null | undefined
  approvalNavigation: ApprovalNavigation
  currentApprovalIndex: number
  approvalCount: number
  onApprovalClose: () => void
  onApprovalDecisionSubmitted: () => void
  onNavigate: (path: string) => void
}>

export function ExecutionDetailSidePanel({
  formPromptPanelOpen,
  currentFormPrompt,
  formPromptNavigation,
  formPromptIndex,
  formPromptCount,
  executionId,
  activityNameMap,
  onFormPromptClose,
  onFormPromptSubmitted,
  workflowDefinition,
  approvalPanelOpen,
  currentApproval,
  approvalMessage,
  approvalNavigation,
  currentApprovalIndex,
  approvalCount,
  onApprovalClose,
  onApprovalDecisionSubmitted,
  onNavigate,
}: ExecutionDetailSidePanelProps) {
  if (formPromptPanelOpen && currentFormPrompt) {
    return (
      <FormPromptSidePanel
        executionId={executionId}
        formPrompt={currentFormPrompt}
        activityNameMap={activityNameMap}
        onClose={onFormPromptClose}
        onSubmitted={onFormPromptSubmitted}
        workflowDefinition={workflowDefinition}
        currentIndex={formPromptIndex}
        totalCount={formPromptCount}
        hasPrev={formPromptNavigation.hasPrev}
        hasNext={formPromptNavigation.hasNext}
        onNavigatePrev={formPromptNavigation.navigatePrev}
        onNavigateNext={formPromptNavigation.navigateNext}
      />
    )
  }

  if (approvalPanelOpen && currentApproval) {
    return (
      <ApprovalSidePanel
        approval={currentApproval}
        message={approvalMessage ?? undefined}
        activityNameMap={activityNameMap}
        onClose={onApprovalClose}
        onDecisionSubmitted={onApprovalDecisionSubmitted}
        onNavigate={onNavigate}
        currentIndex={currentApprovalIndex}
        totalCount={approvalCount}
        hasPrev={approvalNavigation.hasPrev}
        hasNext={approvalNavigation.hasNext}
        onNavigatePrev={approvalNavigation.navigatePrev}
        onNavigateNext={approvalNavigation.navigateNext}
      />
    )
  }

  return null
}
