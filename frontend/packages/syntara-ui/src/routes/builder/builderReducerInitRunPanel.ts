import type { BuilderState } from './builderReducer'

export function initWorkflowRunPanelState(
  state: BuilderState,
  preserveMostRecentRun: boolean | undefined
): Pick<BuilderState, 'mostRecentExecutionId' | 'mostRecentRunPanelOpen' | 'copiedRunActivityIds'> {
  const preserveRun = !!preserveMostRecentRun && state.mostRecentExecutionId != null && state.mostRecentRunPanelOpen
  if (preserveRun) {
    return {
      mostRecentExecutionId: state.mostRecentExecutionId,
      mostRecentRunPanelOpen: state.mostRecentRunPanelOpen,
      copiedRunActivityIds: state.copiedRunActivityIds,
    }
  }
  return {
    mostRecentExecutionId: null,
    mostRecentRunPanelOpen: false,
    copiedRunActivityIds: null,
  }
}
