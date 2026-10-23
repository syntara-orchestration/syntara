import { ActivityTypeEnum, EdgeHandleEnum, TriggerTypeEnum, type Activity, type NodeSettings } from '@syntara/contracts'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import { generateActivityId } from '../../utils/generateUUID'

import type { EdgeConnection } from './types/edge'
import { validateWorkflow } from './utils/validation'
import { validateMinimumWorkflow } from './utils/validation/rules/validateMinimumWorkflow'
import { parseNodeSettings } from './workflowWebMcpSettings'

/** User-selectable workflow nodes in the builder. */
export const WEBMCP_WORKFLOW_NODE_TYPES = [
  ActivityTypeEnum.SCRIPT,
  ActivityTypeEnum.HTTP_REQUEST,
  ActivityTypeEnum.AGENTIC,
  ActivityTypeEnum.AAP_JOB_TEMPLATE,
  ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
  ActivityTypeEnum.APPROVAL,
  ActivityTypeEnum.CONDITION,
  ActivityTypeEnum.LOOP,
  ActivityTypeEnum.CONVERGE,
  ActivityTypeEnum.SWITCH,
  ActivityTypeEnum.WAIT,
] as const

/** Trigger variants exposed by the builder's trigger form. */
export const WEBMCP_WORKFLOW_TRIGGER_TYPES = [
  TriggerTypeEnum.MANUAL_TRIGGER,
  TriggerTypeEnum.SCHEDULED,
  TriggerTypeEnum.WEBHOOK_TRIGGER,
  TriggerTypeEnum.EDA_TRIGGER,
] as const

/** Kept for the simple ordered-step input accepted by earlier tool versions. */
export const WEBMCP_WORKFLOW_STEP_TYPES = [
  ActivityTypeEnum.AGENTIC,
  ActivityTypeEnum.APPROVAL,
  ActivityTypeEnum.AAP_JOB_TEMPLATE,
  ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
  ActivityTypeEnum.HTTP_REQUEST,
] as const

const FORBIDDEN_PARAMETER_KEYS = new Set(['__proto__', 'prototype', 'constructor'])
const SECRET_PARAMETER_KEY = /password|secret|token|authorization|api[_-]?key|cookie/i
const MAX_STEP_COUNT = 10
const MAX_NODE_COUNT = 50
const MAX_TRIGGER_COUNT = 10
const MAX_EDGE_COUNT = 100
const MAX_PARAMETER_LENGTH = 50_000
const TRIGGER_REFERENCE_PATTERN = /^trigger-(\d+)$/
const CASE_HANDLE_PATTERN = /^case_\d+$/
const SOURCE_HANDLE_VALUES = new Set<string>([
  EdgeHandleEnum.SOURCE,
  EdgeHandleEnum.LOOP,
  EdgeHandleEnum.TRUE,
  EdgeHandleEnum.FALSE,
  EdgeHandleEnum.APPROVED,
  EdgeHandleEnum.REJECTED,
  EdgeHandleEnum.DONE,
  EdgeHandleEnum.DEFAULT,
])

type DraftNodeInput = {
  id: string
  type: (typeof WEBMCP_WORKFLOW_NODE_TYPES)[number]
  name: string
  parameters: Record<string, unknown>
  settings?: NodeSettings
}

type DraftTriggerInput = {
  type: (typeof WEBMCP_WORKFLOW_TRIGGER_TYPES)[number]
  name: string
  parameters: Record<string, unknown>
}

type DraftEdgeInput = {
  source: string
  target: string
  sourceHandle: string
  targetHandle: string
}

type DraftInput = {
  name: string
  description: string
  triggers: DraftTriggerInput[]
  nodes: DraftNodeInput[]
  edges: DraftEdgeInput[]
}

export type WorkflowDraftBuildResult =
  | { ok: true; workflow: WorkflowDefinition; edges: EdgeConnection[]; name: string; description: string }
  | { ok: false; message: string }

export type WorkflowValidationSummary = {
  errors: string[]
  warnings: string[]
  readyToRun: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value) as unknown
  return prototype === Object.prototype || prototype === null
}

function isControlCodePoint(codePoint: number): boolean {
  return (
    codePoint <= 0x1f ||
    (codePoint >= 0x7f && codePoint <= 0x9f) ||
    (codePoint >= 0x200e && codePoint <= 0x200f) ||
    (codePoint >= 0x202a && codePoint <= 0x202e) ||
    (codePoint >= 0x2066 && codePoint <= 0x2069)
  )
}

function stripControlCharacters(value: string): string {
  return Array.from(value)
    .filter((character) => {
      const codePoint = character.codePointAt(0)
      return codePoint !== undefined && !isControlCodePoint(codePoint)
    })
    .join('')
}

function cleanText(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== 'string') throw new Error(`${label} must be text.`)
  const cleaned = stripControlCharacters(value).trim()
  if (cleaned.length === 0) throw new Error(`${label} is required.`)
  if (cleaned.length > maxLength) throw new Error(`${label} must be ${maxLength} characters or fewer.`)
  return cleaned
}

function validateJsonArray(value: unknown[], path: string, depth: number, ancestors: WeakSet<object>): void {
  if (value.length > 100) throw new Error(`${path} has too many items.`)
  if (ancestors.has(value)) throw new Error(`${path} must not contain circular values.`)
  ancestors.add(value)
  value.forEach((item, index) => validateJsonValue(item, `${path}[${index}]`, depth + 1, ancestors))
  ancestors.delete(value)
}

function validateJsonObject(
  value: Record<string, unknown>,
  path: string,
  depth: number,
  ancestors: WeakSet<object>
): void {
  if (ancestors.has(value)) throw new Error(`${path} must not contain circular values.`)
  ancestors.add(value)
  if (typeof value.key === 'string' && SECRET_PARAMETER_KEY.test(value.key)) {
    throw new Error(`${path}.${value.key} may contain a secret. Use a Syntara credential reference instead.`)
  }
  for (const [key, item] of Object.entries(value)) {
    if (FORBIDDEN_PARAMETER_KEYS.has(key)) throw new Error(`${path} contains a reserved property.`)
    if (SECRET_PARAMETER_KEY.test(key)) {
      throw new Error(`${path}.${key} may contain a secret. Use a Syntara credential reference instead.`)
    }
    validateJsonValue(item, `${path}.${key}`, depth + 1, ancestors)
  }
  ancestors.delete(value)
}

function validateJsonValue(value: unknown, path: string, depth = 0, ancestors = new WeakSet<object>()): void {
  if (depth > 10) throw new Error(`${path} is nested too deeply.`)
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return
  if (typeof value === 'number' && Number.isFinite(value)) return
  if (Array.isArray(value)) return validateJsonArray(value, path, depth, ancestors)
  if (!isRecord(value)) throw new Error(`${path} must contain JSON values only.`)
  validateJsonObject(value, path, depth, ancestors)
}

function copyParameterObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${path} must be an object.`)
  validateJsonValue(value, path)
  return structuredClone(value)
}

function isValidEntityId(value: string): boolean {
  return (
    value.length <= 255 &&
    /^[a-zA-Z0-9](?:[a-zA-Z0-9_.-]{0,253}[a-zA-Z0-9_])?$/.test(value) &&
    !value.includes('..') &&
    !TRIGGER_REFERENCE_PATTERN.test(value)
  )
}

function cleanEntityId(value: unknown, label: string): string {
  const id = cleanText(value, label, 255)
  if (!isValidEntityId(id)) {
    throw new Error(
      `${label} must use letters, numbers, underscores, periods, or hyphens and cannot look like a trigger reference.`
    )
  }
  return id
}

function findSupportedType<T extends readonly string[]>(types: T, value: unknown): T[number] | null {
  if (typeof value !== 'string') return null
  return types.find((type) => type === value) ?? null
}

function getDefaultTriggerName(type: DraftTriggerInput['type']): string {
  switch (type) {
    case TriggerTypeEnum.MANUAL_TRIGGER:
      return 'Manual Trigger'
    case TriggerTypeEnum.SCHEDULED:
      return 'Scheduled Trigger'
    case TriggerTypeEnum.WEBHOOK_TRIGGER:
      return 'Webhook Trigger'
    case TriggerTypeEnum.EDA_TRIGGER:
      return 'EDA Trigger'
  }
}

function parseTriggers(value: unknown): DraftTriggerInput[] {
  if (value === undefined) {
    return [{ type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Manual Trigger', parameters: {} }]
  }
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_TRIGGER_COUNT) {
    throw new Error(`Provide between 1 and ${MAX_TRIGGER_COUNT} workflow triggers.`)
  }

  return value.map((trigger, index) => {
    if (!isRecord(trigger)) throw new Error(`Trigger ${index + 1} must be an object.`)
    const type = findSupportedType(WEBMCP_WORKFLOW_TRIGGER_TYPES, trigger.type)
    if (!type) throw new Error(`Trigger ${index + 1} has an unsupported type.`)
    const name =
      trigger.name === undefined
        ? getDefaultTriggerName(type)
        : cleanText(trigger.name, `Trigger ${index + 1} name`, 255)
    const parameters =
      trigger.parameters === undefined ? {} : copyParameterObject(trigger.parameters, `Trigger ${index + 1} parameters`)
    return { type, name, parameters }
  })
}

function parseGraphNodes(value: unknown): DraftNodeInput[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_NODE_COUNT) {
    throw new Error(`Provide between 1 and ${MAX_NODE_COUNT} workflow nodes.`)
  }

  const seenIds = new Set<string>()
  return value.map((node, index) => {
    if (!isRecord(node)) throw new Error(`Node ${index + 1} must be an object.`)
    const id = cleanEntityId(node.id, `Node ${index + 1} ID`)
    if (seenIds.has(id)) throw new Error(`Node ID "${id}" is used more than once.`)
    seenIds.add(id)

    const type = findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, node.type)
    if (!type) throw new Error(`Node ${index + 1} has an unsupported type.`)
    const name = cleanText(node.name, `Node ${index + 1} name`, 255)
    const parameters =
      node.parameters === undefined ? {} : copyParameterObject(node.parameters, `Node ${index + 1} parameters`)
    const settings = parseNodeSettings(node.settings, `Node ${index + 1} settings`)
    return { id, type, name, parameters, ...(settings && { settings }) }
  })
}

function parseLegacySteps(value: unknown): DraftNodeInput[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_STEP_COUNT) {
    throw new Error(`Provide between 1 and ${MAX_STEP_COUNT} ordered workflow steps, or use graph nodes and edges.`)
  }
  return value.map((step, index) => {
    if (!isRecord(step)) throw new Error(`Step ${index + 1} must be an object.`)
    const type = findSupportedType(WEBMCP_WORKFLOW_STEP_TYPES, step.type)
    if (!type)
      throw new Error(`Step ${index + 1} has an unsupported type. Use graph nodes and edges for other node types.`)
    const name = cleanText(step.name, `Step ${index + 1} name`, 255)
    const parameters =
      step.parameters === undefined ? {} : copyParameterObject(step.parameters, `Step ${index + 1} parameters`)
    const settings = parseNodeSettings(step.settings, `Step ${index + 1} settings`)
    return { id: generateActivityId(type), type, name, parameters, ...(settings && { settings }) }
  })
}

function getNodeById(nodes: DraftNodeInput[], id: string): DraftNodeInput | undefined {
  return nodes.find((node) => node.id === id)
}

function getSwitchHandles(node: DraftNodeInput): Set<string> {
  const cases = node.parameters.cases
  if (!Array.isArray(cases)) return new Set([EdgeHandleEnum.DEFAULT])
  const handles = cases.flatMap((caseValue) => {
    if (!isRecord(caseValue) || typeof caseValue.port !== 'string' || !CASE_HANDLE_PATTERN.test(caseValue.port))
      return []
    return [caseValue.port]
  })
  if (node.parameters.default_port === undefined || node.parameters.default_port === EdgeHandleEnum.DEFAULT) {
    handles.push(EdgeHandleEnum.DEFAULT)
  }
  return new Set(handles)
}

function getDefaultSourceHandle(node: DraftNodeInput | DraftTriggerInput): string {
  if (node.type === ActivityTypeEnum.CONDITION) return EdgeHandleEnum.TRUE
  if (node.type === ActivityTypeEnum.APPROVAL) return EdgeHandleEnum.APPROVED
  if (node.type === ActivityTypeEnum.LOOP) return EdgeHandleEnum.LOOP
  if (node.type === ActivityTypeEnum.SWITCH) {
    const switchHandles = getSwitchHandles(node)
    return [...switchHandles].find((handle) => CASE_HANDLE_PATTERN.test(handle)) ?? EdgeHandleEnum.DEFAULT
  }
  return EdgeHandleEnum.SOURCE
}

function validateSourceHandle(node: DraftNodeInput | DraftTriggerInput, handle: string): void {
  if (WEBMCP_WORKFLOW_TRIGGER_TYPES.some((triggerType) => triggerType === node.type)) {
    if (handle !== EdgeHandleEnum.SOURCE) throw new Error('Trigger edges must use the default "source" source_handle.')
    return
  }
  if (node.type === ActivityTypeEnum.CONDITION && handle !== EdgeHandleEnum.TRUE && handle !== EdgeHandleEnum.FALSE) {
    throw new Error('Condition node edges must use the "true" or "false" source_handle.')
  }
  if (
    node.type === ActivityTypeEnum.APPROVAL &&
    handle !== EdgeHandleEnum.APPROVED &&
    handle !== EdgeHandleEnum.REJECTED
  ) {
    throw new Error('Approval node edges must use the "approved" or "rejected" source_handle.')
  }
  if (node.type === ActivityTypeEnum.LOOP && handle !== EdgeHandleEnum.LOOP && handle !== EdgeHandleEnum.DONE) {
    throw new Error('Loop node edges must use the "loop" or "done" source_handle.')
  }
  if (node.type === ActivityTypeEnum.SWITCH && !getSwitchHandles(node).has(handle)) {
    throw new Error(`Switch node edge source_handle "${handle}" must match a configured case port or default port.`)
  }
  if (
    node.type !== ActivityTypeEnum.CONDITION &&
    node.type !== ActivityTypeEnum.APPROVAL &&
    node.type !== ActivityTypeEnum.LOOP &&
    node.type !== ActivityTypeEnum.SWITCH &&
    handle !== EdgeHandleEnum.SOURCE
  ) {
    throw new Error(`Node type "${node.type}" only supports the default "source" handle.`)
  }
}

function parseSourceHandle(value: unknown, source: string, sourceNode: DraftNodeInput | DraftTriggerInput): string {
  const handle =
    value === undefined
      ? getDefaultSourceHandle(sourceNode)
      : cleanText(value, `Edge from ${source} source_handle`, 255)
  if (!SOURCE_HANDLE_VALUES.has(handle) && !CASE_HANDLE_PATTERN.test(handle)) {
    throw new Error(`Edge from "${source}" has an unsupported source_handle.`)
  }
  validateSourceHandle(sourceNode, handle)
  return handle
}

function cleanEdgeSource(value: unknown, label: string): string {
  const source = cleanText(value, label, 255)
  if (TRIGGER_REFERENCE_PATTERN.test(source)) return source
  if (!isValidEntityId(source)) {
    throw new Error(`${label} must be a node ID or a trigger reference such as "trigger-0".`)
  }
  return source
}

function parseGraphEdges(value: unknown, nodes: DraftNodeInput[], triggers: DraftTriggerInput[]): DraftEdgeInput[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_EDGE_COUNT) {
    throw new Error(`Provide between 1 and ${MAX_EDGE_COUNT} workflow edges for graph nodes.`)
  }

  const edges = value.map((edge, index) => {
    if (!isRecord(edge)) throw new Error(`Edge ${index + 1} must be an object.`)
    const source = cleanEdgeSource(edge.source, `Edge ${index + 1} source`)
    const target = cleanEntityId(edge.target, `Edge ${index + 1} target`)
    const triggerMatch = TRIGGER_REFERENCE_PATTERN.exec(source)
    let sourceNode: DraftNodeInput | DraftTriggerInput | undefined
    if (triggerMatch) {
      const triggerIndex = Number(triggerMatch[1])
      sourceNode = triggers[triggerIndex]
      if (!sourceNode) throw new Error(`Edge ${index + 1} refers to missing trigger "${source}".`)
    } else {
      sourceNode = getNodeById(nodes, source)
      if (!sourceNode)
        throw new Error(`Edge ${index + 1} source "${source}" does not match a workflow node or trigger reference.`)
    }

    const targetNode = getNodeById(nodes, target)
    if (!targetNode) throw new Error(`Edge ${index + 1} target "${target}" does not match a workflow node.`)
    const sourceHandle = parseSourceHandle(edge.source_handle, source, sourceNode)
    const targetHandle =
      edge.target_handle === undefined
        ? EdgeHandleEnum.TARGET
        : cleanText(edge.target_handle, `Edge ${index + 1} target_handle`, 255)
    if (targetHandle !== EdgeHandleEnum.TARGET && targetHandle !== EdgeHandleEnum.END) {
      throw new Error(`Edge ${index + 1} target_handle must be "target" or "end".`)
    }
    if (targetHandle === EdgeHandleEnum.END && targetNode.type !== ActivityTypeEnum.LOOP) {
      throw new Error(`Edge ${index + 1} may use target_handle "end" only when connecting back to a loop node.`)
    }
    return { source, target, sourceHandle, targetHandle }
  })

  const uniqueEdges = new Set<string>()
  for (const edge of edges) {
    const key = `${edge.source}:${edge.sourceHandle}->${edge.target}:${edge.targetHandle}`
    if (uniqueEdges.has(key)) throw new Error(`The edge from "${edge.source}" to "${edge.target}" is duplicated.`)
    uniqueEdges.add(key)
  }
  return edges
}

function buildLinearEdges(nodes: DraftNodeInput[]): DraftEdgeInput[] {
  return nodes.map((node, index) => {
    const previous = index === 0 ? null : nodes[index - 1]
    return {
      source: previous?.id ?? 'trigger-0',
      target: node.id,
      sourceHandle: previous ? getDefaultSourceHandle(previous) : EdgeHandleEnum.SOURCE,
      targetHandle: EdgeHandleEnum.TARGET,
    }
  })
}

function parseDraftInput(input: unknown): DraftInput {
  if (!isRecord(input))
    throw new Error('Provide a workflow name, description, and either ordered steps or graph nodes and edges.')

  const name = cleanText(input.name, 'Workflow name', 255)
  if (typeof input.description !== 'string') throw new Error('Workflow description must be text.')
  const description = stripControlCharacters(input.description).trim()
  if (description.length > 1024) throw new Error('Workflow description must be 1024 characters or fewer.')

  const hasSteps = Object.hasOwn(input, 'steps')
  const hasNodes = Object.hasOwn(input, 'nodes')
  if (hasSteps === hasNodes) throw new Error('Provide either ordered "steps" or graph "nodes" with "edges", not both.')

  const triggers = parseTriggers(input.triggers)
  if (hasSteps) {
    if (Object.hasOwn(input, 'edges'))
      throw new Error(
        'The ordered "steps" format creates its own edges. Use graph "nodes" and "edges" for custom connections.'
      )
    if (triggers.length !== 1)
      throw new Error(
        'The ordered "steps" format supports one trigger. Use graph "nodes" and "edges" for multiple triggers.'
      )
    const nodes = parseLegacySteps(input.steps)
    return { name, description, triggers, nodes, edges: buildLinearEdges(nodes) }
  }

  if (!Object.hasOwn(input, 'edges'))
    throw new Error('Graph nodes need explicit "edges" that connect triggers, branches, and steps.')
  const nodes = parseGraphNodes(input.nodes)
  const edges = parseGraphEdges(input.edges, nodes, triggers)
  return { name, description, triggers, nodes, edges }
}

export function buildWorkflowDraft(
  input: unknown,
  currentWorkflow: WorkflowDefinition | null,
  currentEdges: EdgeConnection[]
): WorkflowDraftBuildResult {
  if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading. Try again shortly.' }
  const activities = currentWorkflow.workflow.activities
  if (activities.length > 0 || (currentWorkflow.triggers?.length ?? 0) > 0 || currentEdges.length > 0) {
    return { ok: false, message: 'Draft creation is available on an empty workflow builder.' }
  }

  try {
    const draft = parseDraftInput(input)
    const triggers: Activity[] = draft.triggers.map((trigger) => ({
      id: generateActivityId('trigger'),
      type: trigger.type,
      name: trigger.name,
      parameters: trigger.parameters,
    }))
    const newActivities: Activity[] = draft.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      name: node.name,
      parameters: node.parameters,
      ...(node.settings && { settings: node.settings }),
    }))
    const edges: EdgeConnection[] = draft.edges.map((edge) => ({
      id: generateActivityId('edge'),
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    }))

    const totalLength = JSON.stringify({ triggers, nodes: newActivities, edges }).length
    if (totalLength > MAX_PARAMETER_LENGTH) throw new Error('Workflow node configuration is too large.')

    return {
      ok: true,
      name: draft.name,
      description: draft.description,
      workflow: {
        ...currentWorkflow,
        name: draft.name,
        description: draft.description,
        triggers,
        workflow: { ...currentWorkflow.workflow, activities: newActivities },
      },
      edges,
    }
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : 'The workflow draft could not be created.',
    }
  }
}

export function validateWorkflowDraft(
  activities: Activity[],
  edges: EdgeConnection[],
  triggers: Activity[]
): WorkflowValidationSummary {
  const minimumErrors = validateMinimumWorkflow(activities, edges, triggers)
  const structural = validateWorkflow(activities, edges, { triggers })
  const errors = [...minimumErrors, ...structural.errors].map((finding) => finding.message)
  const warnings = structural.warnings.map((finding) => finding.message)
  return { errors, warnings, readyToRun: errors.length === 0 }
}
