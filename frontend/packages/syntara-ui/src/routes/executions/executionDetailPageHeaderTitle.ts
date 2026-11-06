import type { ExecutionsAPI } from '@syntara/contracts'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']

type WorkflowDefinitionLike = {
  name?: string
  metadata?: { name?: string; description?: string }
}

export function executionDetailPageHeading(execution: Execution | undefined, executionId: string): string {
  const wfDef = execution?.workflow_definition as unknown as WorkflowDefinitionLike | undefined
  return wfDef?.metadata?.name ?? wfDef?.name ?? `Execution ${executionId.slice(0, 8)}...`
}

export function executionDetailHasTitleRowExtras(execution: Execution | undefined): boolean {
  return Boolean(execution?.status || execution?.created_at)
}

export function executionHasParentRun(execution: Execution | undefined): boolean {
  return typeof execution?.execution_metadata?.parent_execution_id === 'string'
}
