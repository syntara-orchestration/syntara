import { canvasNodeIdFromApprovalNodeId } from '../../approvals/approvalNodeId'

export type WorkflowDefinitionLike = {
  nodes?: Array<{ id?: unknown; type?: unknown }>
  workflow?: { activities?: Array<{ id?: unknown; type?: unknown }> }
}

/** Resolve canvas step type from workflow definition by node or activity id. */
export function resolveCanvasNodeType(
  canvasOrActivityId: string,
  workflowDefinition: WorkflowDefinitionLike | undefined
): string | undefined {
  if (!workflowDefinition) return undefined
  const canvasId = canvasNodeIdFromApprovalNodeId(canvasOrActivityId)
  const nodes = workflowDefinition.nodes ?? workflowDefinition.workflow?.activities ?? []
  const match = nodes.find((node) => node.id === canvasId || node.id === canvasOrActivityId)
  return typeof match?.type === 'string' ? match.type : undefined
}
