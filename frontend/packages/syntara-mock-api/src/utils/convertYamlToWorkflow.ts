import { WorkflowVersionStatusEnum, type WorkflowAPI } from '@syntara/contracts'
import { readFileSync } from 'fs'
import yaml from 'js-yaml'
import { basename, isAbsolute, relative, resolve } from 'path'

import { mockDate } from '../resources/mockDates'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type WorkflowDefinition = WorkflowAPI.components['schemas']['WorkflowDefinition']
type V2Edge = { from: string; to: string; from_port?: string; to_port?: string }

type YamlEdge = {
  from?: string
  to?: string
  source?: string
  target?: string
  from_port?: string
  to_port?: string
  /** YAML examples use `port` where the API uses `from_port` (e.g. then/else/body). */
  port?: string
}

const YAML_PORT_TO_FROM_PORT: Record<string, V2Edge['from_port']> = {
  then: 'true',
  else: 'false',
  body: 'iterate',
}

const VALID_FROM_PORTS = new Set<string>(['true', 'false', 'iterate', 'complete', 'approved', 'rejected'])
const VALID_TO_PORTS = new Set<string>(['iterate'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || typeof value === 'string'
}

function isYamlEdge(value: unknown): value is YamlEdge {
  if (!isRecord(value)) return false
  return (
    isOptionalString(value.from) &&
    isOptionalString(value.to) &&
    isOptionalString(value.source) &&
    isOptionalString(value.target) &&
    isOptionalString(value.from_port) &&
    isOptionalString(value.to_port) &&
    isOptionalString(value.port)
  )
}

function isValidFromPort(value: string): value is NonNullable<V2Edge['from_port']> {
  return VALID_FROM_PORTS.has(value)
}

function isValidToPort(value: string): value is NonNullable<V2Edge['to_port']> {
  return VALID_TO_PORTS.has(value)
}

function yamlPortToFromPort(port: string | undefined): V2Edge['from_port'] | undefined {
  if (!port) return undefined
  const mapped = YAML_PORT_TO_FROM_PORT[port] ?? port
  return isValidFromPort(mapped) ? mapped : undefined
}

function yamlPortToToPort(port: string | undefined): V2Edge['to_port'] | undefined {
  if (!port) return undefined
  return isValidToPort(port) ? port : undefined
}

function isWorkflowDefinition(value: unknown): value is WorkflowDefinition {
  if (!isRecord(value)) return false

  for (const field of ['triggers', 'nodes'] as const) {
    const fieldValue = value[field]
    if (fieldValue !== undefined && !Array.isArray(fieldValue)) return false
  }

  const edgesValue = value.edges
  if (edgesValue !== undefined && !Array.isArray(edgesValue)) return false

  if (Array.isArray(edgesValue)) {
    return edgesValue.every(isYamlEdge)
  }

  return true
}

function parseYamlWorkflowDefinition(value: unknown, yamlFilePath: string): WorkflowDefinition {
  if (!isWorkflowDefinition(value)) {
    throw new Error(`Invalid workflow YAML in ${yamlFilePath}: root must be a workflow definition object`)
  }
  return value
}

function normalizeYamlEdge(edge: YamlEdge): V2Edge | null {
  const from = edge.from ?? edge.source
  const to = edge.to ?? edge.target
  if (!from || !to) return null

  const fromPort = yamlPortToFromPort(edge.from_port ?? edge.port)
  const toPort = yamlPortToToPort(edge.to_port)

  return {
    from,
    to,
    ...(fromPort ? { from_port: fromPort } : {}),
    ...(toPort ? { to_port: toPort } : {}),
  }
}

/**
 * Example YAML often omits trigger→entry edges. Connect each trigger to workflow
 * entry nodes (nodes with no incoming edges from other nodes).
 */
function inferMissingTriggerEdges(definition: WorkflowDefinition, edges: V2Edge[]): V2Edge[] {
  const def = definition as Record<string, unknown>
  const triggers = (def.triggers ?? []) as Array<{ id?: string }>
  const nodes = (def.nodes ?? []) as Array<{ id?: string }>

  const triggerIds = triggers.map((t) => t.id).filter((id): id is string => !!id)
  const nodeIds = new Set(nodes.map((n) => n.id).filter((id): id is string => !!id))
  if (triggerIds.length === 0 || nodeIds.size === 0) return edges

  const targets = new Set(edges.map((e) => e.to).filter((id) => nodeIds.has(id)))
  const entryNodeIds = [...nodeIds].filter((id) => !targets.has(id))
  if (entryNodeIds.length === 0) return edges

  const existing = new Set(edges.map((e) => `${e.from}\0${e.to}`))
  const inferred: V2Edge[] = []

  for (const triggerId of triggerIds) {
    for (const entryId of entryNodeIds) {
      const key = `${triggerId}\0${entryId}`
      if (!existing.has(key)) {
        inferred.push({ from: triggerId, to: entryId })
        existing.add(key)
      }
    }
  }

  return [...edges, ...inferred]
}

function parseYamlEdges(edges: unknown): YamlEdge[] {
  if (edges === undefined) return []
  if (!Array.isArray(edges)) return []
  return edges.filter(isYamlEdge)
}

/** Normalize example YAML into API-shaped workflow definitions for the mock API. */
function normalizeWorkflowDefinition(definition: WorkflowDefinition): WorkflowDefinition {
  const rawEdges = parseYamlEdges(definition.edges)
  const normalizedEdges = rawEdges.map(normalizeYamlEdge).filter((edge): edge is V2Edge => edge != null)
  const edges = inferMissingTriggerEdges(definition, normalizedEdges)

  return { ...definition, edges }
}

function assertPathWithinBase(filePath: string, baseDir: string): string {
  const resolvedBase = resolve(baseDir)
  const resolvedPath = resolve(filePath)
  const rel = relative(resolvedBase, resolvedPath)
  if (rel.startsWith('..') || isAbsolute(rel)) {
    throw new Error(`Refusing to read YAML outside ${resolvedBase}: ${filePath}`)
  }
  return resolvedPath
}

/**
 * Convert a YAML workflow definition file to a WorkflowWithVersion object
 *
 * @param yamlFilePath - Path to the YAML workflow file
 * @param id - Unique workflow ID
 * @param createdBy - Creator of the workflow as UserReference (default: demo user)
 * @param allowedBaseDir - Base directory to restrict file access (required for security)
 */
export function convertYamlToWorkflow(
  yamlFilePath: string,
  id: string,
  createdBy: { id: string; name: string } = { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'demo' },
  allowedBaseDir: string
): WorkflowWithVersion {
  const resolvedPath = assertPathWithinBase(yamlFilePath, allowedBaseDir)
  const yamlContent = readFileSync(resolvedPath, 'utf-8')
  // js-yaml 4 rejects unsafe tags (e.g. !!js/function) by default; safeLoad was removed.
  const parsedDefinition = parseYamlWorkflowDefinition(yaml.load(yamlContent), yamlFilePath)
  const workflowDefinition = normalizeWorkflowDefinition(parsedDefinition)

  const filename = basename(yamlFilePath, '.yaml')
  const def = workflowDefinition as Record<string, unknown>
  const name = (def.name as string) || workflowDefinition.metadata?.name || filename
  const description = (def.description as string) || workflowDefinition.metadata?.description || `Workflow: ${name}`

  return {
    id,
    name,
    description,
    created_at: mockDate.daysAgo3,
    updated_at: mockDate.daysAgo1,
    created_by: createdBy,
    updated_by: createdBy,
    labels: {},
    current_version: 1,
    is_enabled: false,
    published_version_id: null,
    version: {
      // Deterministic, stable version id/workflow_id — derived from the workflow's own
      // id (itself derived from the file path, see workflows.ts) rather than a random
      // UUID. Publish handlers key off version.id (see handlers.ts publish endpoint);
      // a missing id here silently no-ops "publish" for every YAML-seeded workflow.
      id: `${id}-v1`,
      workflow_id: id,
      workflow_definition: workflowDefinition,
      version: 1,
      schema_version: '2.0.0',
      status: WorkflowVersionStatusEnum.DRAFT,
      created_by: createdBy.id,
      created_by_username: createdBy.name,
      created_at: mockDate.daysAgo3,
      updated_at: mockDate.daysAgo3,
    },
  }
}
