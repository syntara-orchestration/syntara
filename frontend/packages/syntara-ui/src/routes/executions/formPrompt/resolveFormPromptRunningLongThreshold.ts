import { canvasNodeIdFromPromptNodeId } from './formPromptNodeId'
import type { WorkflowDefinitionLike } from './resolveCanvasNodeType'

/** Matches FormPromptNodeForm settings default for "Expected duration (seconds)". */
const FORM_PROMPT_RUNNING_LONG_DEFAULT_SECONDS = 600

type ActivityWithSettings = {
  id?: unknown
  settings?: { timeout?: number | null }
}

/** Expected duration before the execution UI shows a "Running long" warning (node settings.timeout). */
export function resolveFormPromptRunningLongThresholdSeconds(
  promptNodeId: string,
  workflowDefinition: WorkflowDefinitionLike | undefined
): number {
  const canvasId = canvasNodeIdFromPromptNodeId(promptNodeId)
  const nodes = (workflowDefinition?.nodes ?? workflowDefinition?.workflow?.activities ?? []) as ActivityWithSettings[]
  const node = nodes.find((entry) => entry.id === canvasId || entry.id === promptNodeId)
  const timeout = node?.settings?.timeout
  if (typeof timeout === 'number' && timeout > 0) {
    return timeout
  }
  return FORM_PROMPT_RUNNING_LONG_DEFAULT_SECONDS
}
