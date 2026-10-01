import type { Approval, FormsAPI } from '@syntara/contracts'

import { canvasNodeIdFromApprovalNodeId } from '../approvals/approvalNodeId'

import { canvasNodeIdFromPromptNodeId } from './formPrompt/formPromptNodeId'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

export function resolveWaitingNodeHighlightId(
  currentFormPrompt: FormPromptSummary | null,
  currentApproval: Approval | null | undefined
): string | undefined {
  if (currentFormPrompt) {
    return canvasNodeIdFromPromptNodeId(currentFormPrompt.prompt_node_id)
  }
  if (currentApproval) {
    return canvasNodeIdFromApprovalNodeId(currentApproval.approval_node_id)
  }
  return undefined
}
