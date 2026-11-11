/**
 * Resolves the child-execution reference for a sub-workflow node.
 *
 * While the child is running the reference lives in the node's
 * ``runtime_metadata`` (``child_execution_id`` + ``child_workflow_name``); once
 * the node reaches a terminal state the reference is also persisted to
 * ``output_data`` (``child_execution_id`` + ``workflow_name``).
 *
 * Prefers ``runtimeMetadata`` so the child run is reachable while it is still
 * running, and falls back to ``outputData`` when runtime metadata is absent or
 * carries no usable child reference (for example for_each nodes, where runtime
 * metadata is not populated). Returns null when neither source has a child yet,
 * so callers render nothing. The fallback never selects a "latest" child across
 * iterations — it only reads the single reference present in each source.
 */
export function extractSubWorkflowChild(
  runtimeMetadata: Record<string, unknown> | null | undefined,
  outputData: Record<string, unknown> | null | undefined
): { childExecutionId: string; childName: string | null } | null {
  return readChildReference(runtimeMetadata, 'child_workflow_name') ?? readChildReference(outputData, 'workflow_name')
}

function readChildReference(
  source: Record<string, unknown> | null | undefined,
  nameKey: 'child_workflow_name' | 'workflow_name'
): { childExecutionId: string; childName: string | null } | null {
  if (!source) return null
  const childExecutionId = source.child_execution_id
  if (typeof childExecutionId !== 'string' || childExecutionId.length === 0) return null
  const childName = source[nameKey]
  return { childExecutionId, childName: typeof childName === 'string' ? childName : null }
}
