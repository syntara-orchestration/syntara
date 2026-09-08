import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import type { ValidationError } from '../types'

/**
 * Information about a condition branch in the trace
 */
type ConditionBranchInfo = {
  conditionId: string
  conditionName: string
  branch: 'then' | 'else'
}

function resolveConditionBranchFromHandle(sourceHandle: string | null | undefined): 'then' | 'else' | null {
  if (sourceHandle === EdgeHandleEnum.TRUE) return 'then'
  if (sourceHandle === EdgeHandleEnum.FALSE) return 'else'
  return null
}

/**
 * Traces backwards from a node to find all condition branches it originates from.
 *
 * This recursively follows edges backwards until reaching:
 * - A condition node (record which branch was taken)
 * - A node with no incoming edges (entry point)
 * - A node already visited (cycle detection)
 */
function traceToConditions(
  nodeId: string,
  edges: EdgeConnection[],
  activities: Activity[],
  visited: Set<string> = new Set()
): ConditionBranchInfo[] {
  // Prevent infinite loops
  if (visited.has(nodeId)) {
    return []
  }
  visited.add(nodeId)

  const results: ConditionBranchInfo[] = []

  // Find all incoming edges to this node
  const incomingEdges = edges.filter((e) => e.target === nodeId)

  for (const edge of incomingEdges) {
    const sourceNode = activities.find((a) => a.id === edge.source)
    if (!sourceNode) continue

    // If source is a condition node, record which branch we came from
    if (sourceNode.type === ActivityTypeEnum.CONDITION) {
      const branch = resolveConditionBranchFromHandle(edge.sourceHandle)
      if (branch) {
        results.push({
          conditionId: sourceNode.id,
          conditionName: sourceNode.name ?? sourceNode.id,
          branch,
        })
      }
    }

    // Continue tracing backwards from the source node
    const upstreamConditions = traceToConditions(edge.source, edges, activities, visited)
    results.push(...upstreamConditions)
  }

  return results
}

/**
 * Validates that converge nodes don't receive inputs from both branches of the same condition.
 *
 * If a converge node receives inputs from both the 'then' and 'else' branches of the same
 * condition, it creates logical ambiguity - the converge will always execute regardless of
 * which branch was taken, defeating the purpose of conditional logic.
 *
 * Example of INVALID flow:
 *   Condition A
 *     ├─ Then → Task B ──┐
 *     └─ Else → Task C ──┴─→ Converge D  ❌ Invalid!
 *
 * Example of VALID flow:
 *   Condition A
 *     ├─ Then → Task B → Task E
 *     └─ Else → Task C → Task F
 *   Task E ──┐
 *   Task F ──┴─→ Converge G  ✅ Valid (different conditions)
 */
function addConditionBranch(
  branches: Map<string, Set<'then' | 'else'>>,
  conditionId: string,
  branch: 'then' | 'else'
): void {
  if (!branches.has(conditionId)) {
    branches.set(conditionId, new Set())
  }
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: key was just set via branches.set(conditionId, new Set()) above
  branches.get(conditionId)!.add(branch)
}

function collectConditionBranches(
  convergeId: string,
  edges: EdgeConnection[],
  activities: Activity[]
): Map<string, Set<'then' | 'else'>> {
  const conditionBranches = new Map<string, Set<'then' | 'else'>>()
  const incomingEdges = edges.filter((e) => e.target === convergeId)

  for (const edge of incomingEdges) {
    const sourceNode = activities.find((a) => a.id === edge.source)
    if (sourceNode?.type === ActivityTypeEnum.CONDITION) {
      const branch = resolveConditionBranchFromHandle(edge.sourceHandle)
      if (branch) {
        addConditionBranch(conditionBranches, sourceNode.id, branch)
      }
    }

    const conditions = traceToConditions(edge.source, edges, activities)
    for (const condInfo of conditions) {
      addConditionBranch(conditionBranches, condInfo.conditionId, condInfo.branch)
    }
  }

  return conditionBranches
}

export function validateConvergeInputs(activities: Activity[], edges: EdgeConnection[]): ValidationError[] {
  const errors: ValidationError[] = []
  const convergeNodes = activities.filter((a) => a.type === ActivityTypeEnum.CONVERGE)

  for (const converge of convergeNodes) {
    const conditionBranches = collectConditionBranches(converge.id, edges, activities)

    for (const [conditionId, branches] of conditionBranches.entries()) {
      if (!branches.has('then') || !branches.has('else')) continue

      const conditionNode = activities.find((a) => a.id === conditionId)
      const conditionName = conditionNode?.name ?? conditionId

      errors.push({
        id: `converge-same-condition-${converge.id}-${conditionId}`,
        severity: 'error',
        rule: 'converge-inputs',
        message: `Converge "${converge.name ?? converge.id}" receives inputs from both 'Then' and 'Else' branches of condition "${conditionName}". This creates ambiguous execution flow.`,
        nodeIds: [converge.id, conditionId],
        suggestion:
          'Restructure the workflow so that only one branch of the condition leads to this converge node. ' +
          'If you need both branches to eventually meet, add intermediate nodes and converge at a point ' +
          'where the branches come from different conditions.',
      })
    }
  }

  return errors
}
