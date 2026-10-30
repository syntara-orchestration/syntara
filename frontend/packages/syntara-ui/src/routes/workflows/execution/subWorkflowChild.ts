/**
 * Pulls the child-execution reference out of a sub-workflow node's persisted
 * ``output_data`` (``child_execution_id`` + ``workflow_name``). Returns null when
 * the node has not produced a child yet, so callers render nothing.
 */
export function extractSubWorkflowChild(
  outputData: Record<string, unknown> | null | undefined
): { childExecutionId: string; childName: string | null } | null {
  if (!outputData) return null
  const childExecutionId = outputData.child_execution_id
  if (typeof childExecutionId !== 'string' || childExecutionId.length === 0) return null
  const workflowName = outputData.workflow_name
  return { childExecutionId, childName: typeof workflowName === 'string' ? workflowName : null }
}
