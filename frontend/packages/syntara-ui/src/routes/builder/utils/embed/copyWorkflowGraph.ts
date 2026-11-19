/**
 * Pure graph-copy transform for Embed Mode (SDP R12).
 *
 * Input: a published source workflow definition (the v2 export shape:
 *   { nodes: [{id,type,parameters,position}], edges: [{from,to,from_port?,to_port?}], triggers: [...] }).
 * Output: store-shaped activities + EdgeConnection[] + positions ready for
 *   useWorkflowStore.batchAddActivitiesAndEdges, with every id freshly minted so the
 *   embedded subgraph is unique within the parent and carries NO reference to the source.
 *
 * Guarantees (SDP R12 / Embed Mode AC):
 *  - Source TRIGGER steps are excluded; no new execution entry path is introduced.
 *  - Copied steps get ids unique within the parent (generateActivityId).
 *  - Internal edges and `${...}` expression references are remapped to the copied ids.
 *  - Edges touching an excluded trigger (or any non-copied node) are dropped and counted.
 *  - The original definition is never mutated (deep clone).
 *  - No `sub_workflow` reference node is produced ⇒ no Used-By entry, no child execution.
 *
 * Security (SDP R5 / Feature-Lead instruction): resource references
 *  (credential_id / integration_id / integration_ids / credentials) are DETECTED and
 *  REPORTED via `resourceReferenceNodes`. This module does NOT silently strip or
 *  preserve them as authorized — the caller surfaces them and the embed is gated
 *  pending the authorization-at-use decision (documented OPEN for Sagar/security).
 *
 * NOTE (verify on-computer): this is a DRAFT written without a compiler/test run in the
 * authoring environment. Confirm import paths, the `Activity` shape, and the v2 node
 * `position` field against @syntara/contracts before relying on it.
 */

import type { Activity } from '../../../../stores/workflowStoreTypes'
import { generateActivityId } from '../../../../utils/generateUUID'
import type { EdgeConnection } from '../../types/edge'
import { v2PortToHandle, v2TargetPortToHandle } from '../edgeHelpers'

import { rewriteExpressionReferences } from './rewriteExpressionReferences'

/** Fields on a node's parameters that reference a project-scoped resource. */
const RESOURCE_REFERENCE_FIELDS = ['credential_id', 'integration_id', 'integration_ids', 'credentials'] as const

/** Node type that embeds a runtime child reference — never copied as-is (see subWorkflowNodes). */
const SUB_WORKFLOW_NODE_TYPE = 'sub_workflow'

type V2Node = {
  id: string
  type?: string
  name?: string
  parameters?: Record<string, unknown>
  position?: { x: number; y: number }
  [k: string]: unknown
}

type V2Edge = { from: string; to: string; from_port?: string; to_port?: string }

export type SourceDefinition = {
  nodes?: V2Node[]
  edges?: V2Edge[]
  triggers?: Array<{ id?: string; [k: string]: unknown }>
}

export type CopyWorkflowGraphResult = {
  activities: Activity[]
  edges: EdgeConnection[]
  positions: Record<string, { x: number; y: number }>
  /** old source id -> new parent id, for callers that need provenance. */
  idMap: Map<string, string>
  /** Edges dropped because an endpoint was an excluded trigger / non-copied node. */
  droppedEdgeCount: number
  /** Copied nodes that carry project-scoped resource references (for UI surfacing + gating). */
  resourceReferenceNodes: Array<{ nodeId: string; fields: string[] }>
  /**
   * Copied nodes that are themselves `sub_workflow` reference nodes. Embedding these would
   * re-introduce a live child execution + Used-By dependency, breaking Embed's "snapshot,
   * no child run, no dependency" guarantee, so the caller BLOCKS embed when this is non-empty.
   */
  subWorkflowNodes: Array<{ nodeId: string }>
  /** `${...}` references to a source node that was not copied (e.g. an excluded trigger). */
  danglingExpressionRefs: Array<{ nodeId: string; namespace: string; expression: string }>
}

const DEFAULT_OFFSET = { x: 80, y: 80 }

const RESOURCE_FIELD_SET: ReadonlySet<string> = new Set(RESOURCE_REFERENCE_FIELDS)

/** True when a resource-reference value is actually set (non-empty string / non-empty array / any object). */
function isNonEmptyResource(value: unknown): boolean {
  if (value == null) return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'string') return value !== ''
  return true
}

/**
 * Detect every resource reference in a node's parameters, at ANY depth.
 *
 * Top-level fields (credential_id, …) and nested ones — e.g. agent
 * `integration_connections[].credential_id` / `integration_id` — are both flagged,
 * returning dotted/indexed paths so a leaky security gate can't silently copy them.
 */
function detectResourceFields(parameters: Record<string, unknown> | undefined): string[] {
  if (!parameters) return []
  const found = new Set<string>()
  const visit = (value: unknown, path: string): void => {
    if (value == null || typeof value !== 'object') return
    if (Array.isArray(value)) {
      value.forEach((item, i) => visit(item, `${path}[${i}]`))
      return
    }
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const childPath = path ? `${path}.${key}` : key
      if (RESOURCE_FIELD_SET.has(key) && isNonEmptyResource(child)) found.add(childPath)
      visit(child, childPath)
    }
  }
  visit(parameters, '')
  return [...found]
}

export function copyWorkflowGraph(
  definition: SourceDefinition,
  options?: { positionOffset?: { x: number; y: number } }
): CopyWorkflowGraphResult {
  const offset = options?.positionOffset ?? DEFAULT_OFFSET
  const nodes = definition.nodes ?? []

  // Trigger ids are excluded from the copy (SDP R12: no trigger steps, no new entry path).
  const triggerIds = new Set((definition.triggers ?? []).map((t) => t.id).filter((id): id is string => Boolean(id)))
  const sourceNodes = nodes.filter((n) => Boolean(n.id) && !triggerIds.has(n.id))
  const sourceNodeIds = new Set(sourceNodes.map((n) => n.id))
  // Known source ids for dangling-ref detection = copied nodes + EXCLUDED triggers.
  // A reference to an excluded trigger (or any non-copied source node) is dangling.
  const knownSourceIds = new Set<string>([...sourceNodeIds, ...triggerIds])

  // 1. Fresh id for every copied node.
  const idMap = new Map<string, string>()
  for (const n of sourceNodes) idMap.set(n.id, generateActivityId())

  const resourceReferenceNodes: Array<{ nodeId: string; fields: string[] }> = []
  const subWorkflowNodes: Array<{ nodeId: string }> = []
  const danglingExpressionRefs: Array<{ nodeId: string; namespace: string; expression: string }> = []
  const positions: Record<string, { x: number; y: number }> = {}

  // 2. Clone + re-id + rewrite expressions + detect resource refs.
  const activities: Activity[] = sourceNodes.map((n) => {
    const newId = idMap.get(n.id) as string
    const clone = JSON.parse(JSON.stringify(n)) as V2Node
    clone.id = newId

    const { value: rewrittenParams, danglingRefs } = rewriteExpressionReferences(
      clone.parameters ?? {},
      idMap,
      knownSourceIds
    )
    clone.parameters = rewrittenParams
    for (const d of danglingRefs) {
      danglingExpressionRefs.push({ nodeId: newId, namespace: d.namespace, expression: d.expression })
    }

    const resourceFields = detectResourceFields(clone.parameters)
    if (resourceFields.length > 0) resourceReferenceNodes.push({ nodeId: newId, fields: resourceFields })

    if (n.type === SUB_WORKFLOW_NODE_TYPE) subWorkflowNodes.push({ nodeId: newId })

    if (clone.position && Number.isFinite(clone.position.x) && Number.isFinite(clone.position.y)) {
      positions[newId] = { x: clone.position.x + offset.x, y: clone.position.y + offset.y }
    }

    // position is tracked separately in the store; strip it from the activity payload.
    delete clone.position
    return clone as unknown as Activity
  })

  // 3. Remap internal edges; drop edges touching an excluded/non-copied endpoint.
  let droppedEdgeCount = 0
  const edges: EdgeConnection[] = []
  for (const e of definition.edges ?? []) {
    const source = idMap.get(e.from)
    const target = idMap.get(e.to)
    if (!source || !target) {
      droppedEdgeCount += 1
      continue
    }
    const portSuffix = e.from_port ? `-${e.from_port}` : ''
    edges.push({
      id: `${source}-${target}${portSuffix}`,
      source,
      target,
      sourceHandle: v2PortToHandle(e.from_port),
      targetHandle: v2TargetPortToHandle(e.to_port),
    })
  }

  return {
    activities,
    edges,
    positions,
    idMap,
    droppedEdgeCount,
    resourceReferenceNodes,
    subWorkflowNodes,
    danglingExpressionRefs,
  }
}
