import type { WorkflowWithVersion } from '@syntara/contracts'

/** Prefer the published version number when the mock workflow has one; else current draft version. */
export function mockWorkflowVersionNumber(workflow: WorkflowWithVersion | undefined): number {
  if (!workflow) return 1
  const published = (workflow as { published_version_number?: number | null }).published_version_number
  if (typeof published === 'number' && published > 0) return published
  return workflow.current_version ?? 1
}
