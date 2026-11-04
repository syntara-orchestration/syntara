import { sortActivityOrder, type WorkflowDefShape } from '../../builder/useActivityNameMap'
import type { ActivityState } from '../../workflows/execution/types'

import {
  canvasNodeIdFromPromptNodeId,
  compareFormPromptIterationKeys,
  formPromptIterationSortKey,
} from './formPromptNodeId'

type FormPromptSortable = {
  id: string
  prompt_node_id: string
}

/**
 * Order form prompts for prev/next navigation (workflow run order), not API list order
 * (default `-created_at`, which puts the newest prompt first).
 */
export function sortFormPromptsForNavigation<T extends FormPromptSortable>(
  prompts: T[],
  workflowDefinition: WorkflowDefShape | undefined,
  activityStates: ReadonlyMap<string, ActivityState>
): T[] {
  if (prompts.length <= 1) return prompts

  const orderItems = prompts.map((prompt) => ({
    id: canvasNodeIdFromPromptNodeId(prompt.prompt_node_id),
    name: prompt.prompt_node_id,
  }))

  const sortedItems = sortActivityOrder(orderItems, workflowDefinition?.edges, new Map(activityStates))
  const rank = new Map(sortedItems.map((item, index) => [item.id, index]))

  return [...prompts].sort((left, right) => {
    const leftCanvas = canvasNodeIdFromPromptNodeId(left.prompt_node_id)
    const rightCanvas = canvasNodeIdFromPromptNodeId(right.prompt_node_id)
    const leftRank = rank.get(leftCanvas) ?? rank.get(left.prompt_node_id) ?? Number.MAX_SAFE_INTEGER
    const rightRank = rank.get(rightCanvas) ?? rank.get(right.prompt_node_id) ?? Number.MAX_SAFE_INTEGER
    if (leftRank !== rightRank) return leftRank - rightRank
    return compareFormPromptIterationKeys(formPromptIterationSortKey(left), formPromptIterationSortKey(right))
  })
}

export function normalizeFormPromptNavigationList<T extends FormPromptSortable>(
  prompts: T[],
  selectedPromptId: string | undefined,
  workflowDefinition: WorkflowDefShape | undefined,
  activityStates: ReadonlyMap<string, ActivityState>
): { sorted: T[]; index: number } {
  const sorted = sortFormPromptsForNavigation(prompts, workflowDefinition, activityStates)
  if (!selectedPromptId) {
    return { sorted, index: 0 }
  }
  const index = sorted.findIndex((prompt) => prompt.id === selectedPromptId)
  return { sorted, index: Math.max(index, 0) }
}
