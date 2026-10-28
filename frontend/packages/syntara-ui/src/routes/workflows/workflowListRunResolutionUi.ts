/** Delay before showing the preparing modal so fast manual runs skip the extra step. */
export const WORKFLOW_LIST_RUN_PREPARING_DELAY_MS = 300

export type WorkflowListRunResolutionUiState = {
  runDialogOpen: boolean
  hasWorkflow: boolean
  isResolvingRun: boolean
  runConfirmVisible: boolean
  hasPendingRunInput: boolean
}

/** True while trigger resolution is in flight and no follow-up UI has opened yet. */
export function workflowListRunPreparingCandidate(state: WorkflowListRunResolutionUiState): boolean {
  const { runDialogOpen, hasWorkflow, isResolvingRun, runConfirmVisible, hasPendingRunInput } = state
  return Boolean(runDialogOpen && hasWorkflow) && isResolvingRun && !runConfirmVisible && !hasPendingRunInput
}

/** Whether the run confirmation step should be visible after resolution. */
export function workflowListRunConfirmVisible(runDialogOpen: boolean, runConfirmVisible: boolean): boolean {
  return runDialogOpen && runConfirmVisible
}
