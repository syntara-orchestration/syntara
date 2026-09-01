import type { Activity, WorkflowAPI } from '@syntara/contracts'

import { getActivityMetadata } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'
import type { EdgeConnection } from '../types/edge'

import { v2PortToHandle, v2TargetPortToHandle } from './edgeHelpers'
import { DEFAULT_WORKFLOW_NAME } from './workflowNaming'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

type V2Edge = { from: string; to: string; from_port?: string; to_port?: string }

const MAX_POSITION_COORD = 1_000_000

/**
 * Extract persisted node positions from raw definition nodes/triggers.
 * Validates that x and y are finite numbers within safe rendering bounds.
 */
export function parseNodePositions(rawNodes: Array<Record<string, unknown>>): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = Object.create(null) as Record<
    string,
    { x: number; y: number }
  >
  for (const node of rawNodes) {
    if (typeof node.id !== 'string' || !node.id) continue
    const pos = node.position as { x?: unknown; y?: unknown } | undefined
    if (!pos || !Number.isFinite(pos.x) || !Number.isFinite(pos.y)) continue
    const x = pos.x as number
    const y = pos.y as number
    if (Math.abs(x) > MAX_POSITION_COORD || Math.abs(y) > MAX_POSITION_COORD) continue
    positions[node.id] = { x, y }
  }
  return positions
}

/**
 * Shared conversion: takes raw v2 arrays (nodes, edges, triggers) and produces
 * the flat store representation (activities, EdgeConnection[], trigger ID map).
 */
export function convertV2Definition(
  nodes: Activity[],
  v2Edges: V2Edge[],
  rawTriggers: Array<Record<string, unknown>>
): { flattenedActivities: Activity[]; edges: EdgeConnection[]; triggers: Activity[] } {
  const triggers = rawTriggers.map((t, index) => {
    if (!t.id) {
      return { ...t, id: `${(t.type as string) ?? 'trigger'}_${index}` }
    }
    return t
  }) as Activity[]

  const flattenedActivities = nodes.map((a) => {
    const meta = getActivityMetadata(a)
    if (meta) return { ...a, metadata: meta }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- destructuring to strip metadata
    const { metadata: _unsanitized, ...rest } = a as Activity & { metadata?: unknown }
    return rest
  })

  const triggerIdToDisplayId = new Map<string, string>()
  triggers.forEach((t, index) => {
    const defId = (t as { id?: string }).id
    if (defId) {
      triggerIdToDisplayId.set(defId, buildTriggerNodeId(index))
    }
  })

  const validNodeIds = new Set<string>()
  flattenedActivities.forEach((a) => validNodeIds.add(a.id))
  triggers.forEach((_, index) => validNodeIds.add(buildTriggerNodeId(index)))

  const edges: EdgeConnection[] = v2Edges
    .map((e) => {
      const source = triggerIdToDisplayId.get(e.from) ?? e.from
      const target = triggerIdToDisplayId.get(e.to) ?? e.to
      const portSuffix = e.from_port ? `-${e.from_port}` : ''
      return {
        id: `${source}-${target}${portSuffix}`,
        source,
        target,
        sourceHandle: v2PortToHandle(e.from_port),
        targetHandle: v2TargetPortToHandle(e.to_port),
      }
    })
    .filter((edge) => {
      const sourceExists = validNodeIds.has(edge.source)
      const targetExists = validNodeIds.has(edge.target)
      const isValid = sourceExists && targetExists
      if (!isValid && import.meta.env.DEV) {
        // eslint-disable-next-line no-console
        console.warn(`Filtered orphaned edge: ${edge.id} (${edge.source} -> ${edge.target})`, {
          sourceExists,
          targetExists,
        })
      }
      return isValid
    })

  return { flattenedActivities, edges, triggers }
}

/**
 * Processes a raw workflow-with-version from the API into the internal store
 * representation (flat activities, React Flow edges, init payload).
 */
export function processExistingWorkflow(workflow: WorkflowWithVersion) {
  const workflowDef = workflow.version.workflow_definition

  const rawNodes = (workflowDef.nodes ?? []) as Array<Record<string, unknown>>
  const rawTriggers = (workflowDef.triggers ?? []) as Array<Record<string, unknown>>

  const {
    flattenedActivities,
    edges: generatedEdges,
    triggers,
  } = convertV2Definition(rawNodes as Activity[], (workflowDef.edges ?? []) as V2Edge[], rawTriggers)

  const nodePositions = parseNodePositions([...rawNodes, ...rawTriggers])

  const flattenedWorkflow = {
    ...workflowDef,
    is_builtin: workflow.is_builtin === true,
    triggers,
    workflow: { activities: flattenedActivities },
  } as unknown as WorkflowDefinition

  return {
    flattenedWorkflow,
    generatedEdges,
    nodePositions,
    initPayload: {
      name: workflow.name,
      description: workflow.description ?? workflow.name ?? DEFAULT_WORKFLOW_NAME,
    },
  }
}
