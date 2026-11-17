import type { Approval } from '@syntara/contracts'

import { canvasNodeIdFromApprovalNodeId } from '../approvals/approvalNodeId'

import { canvasNodeIdFromPromptNodeId } from './formPrompt/formPromptNodeId'
import type { FormPromptSummary } from './formPromptTypes'

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
