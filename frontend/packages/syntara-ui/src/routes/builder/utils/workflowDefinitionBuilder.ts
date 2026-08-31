import { ActivityTypeEnum, type Activity } from '@syntara/contracts'

import { parseExpression } from '../../../utils/expressions/parser'
import { serializeExpression } from '../../../utils/expressions/serializer'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { EdgeConnection } from '../types/edge'

import { handleToV2Port } from './edgeHelpers'

// Type guard for Activity with inputs property
function hasInputs(activity: Activity): activity is Activity & { inputs: Record<string, unknown> } {
  return 'inputs' in activity && typeof activity.inputs === 'object' && activity.inputs !== null
}

// Type guard for Activity (trigger) with id property
function hasId(trigger: Activity): trigger is Activity & { id: string } {
  return 'id' in trigger && typeof trigger.id === 'string'
}

function isSwitchCaseArray(val: unknown): val is Array<{ port: string; label: string; condition: string }> {
  return (
    Array.isArray(val) &&
    val.every((c) => typeof c === 'object' && c !== null && 'port' in c && 'label' in c && 'condition' in c)
  )
}

/**
 * Transform approval node approver lists from objects to string arrays.
 * The API returns {id, username}/{id, name} objects but the workflow schema expects string arrays.
 */
export function transformApprovalApprovers(parameters: Record<string, unknown>): Record<string, unknown> {
  const transformed = { ...parameters }

  // Extract usernames from ApproverUserSummary[] -> string[]
  if (parameters.approver_users && Array.isArray(parameters.approver_users)) {
    transformed.approver_users = parameters.approver_users.map((u: unknown) =>
      typeof u === 'object' && u !== null && 'username' in u ? (u as { username: string }).username : String(u)
    )
  }

  // Extract group names from ApproverGroupSummary[] -> string[]
  if (parameters.approver_groups && Array.isArray(parameters.approver_groups)) {
    transformed.approver_groups = parameters.approver_groups.map((g: unknown) =>
      typeof g === 'object' && g !== null && 'name' in g ? (g as { name: string }).name : String(g)
    )
  }

  return transformed
}

/**
 * SECURITY: Validates node/edge IDs to prevent injection attacks.
 * Allows alphanumeric, hyphen, underscore, and period (common ID patterns).
 * Prevents path traversal (../, ..\), SQL injection, script tags, and other malicious patterns.
 */
function isValidId(id: string): boolean {
  if (!id || typeof id !== 'string') return false
  const maxLength = 255
  if (id.length > maxLength) return false
  // SECURITY: Validate allowed characters (alphanumeric, hyphen, underscore, period)
  if (!/^[a-zA-Z0-9_.-]+$/.test(id)) return false
  // SECURITY: Must start and end with a safe character (not dot/hyphen) to prevent path traversal
  const firstChar = id[0]
  const lastChar = id[id.length - 1]
  if (firstChar === '.' || firstChar === '-' || lastChar === '.' || lastChar === '-') return false
  // SECURITY: Reject consecutive dots (path traversal via URL normalization)
  if (id.includes('..')) return false
  return true
}

// SECURITY: Control characters and bidi overrides stripped from user-provided strings
// Includes: C0 (U+0000–U+001F), C1 (U+007F–U+009F), LRM/RLM (U+200E–U+200F),
// bidi embeddings (U+202A–U+202E), and bidi isolates (U+2066–U+2069) to prevent trojan source attacks
// eslint-disable-next-line no-control-regex -- Intentional: stripping control/bidi characters for security
const CONTROL_CHAR_PATTERN = /[\u0000-\u001F\u007F-\u009F\u200E\u200F\u202A-\u202E\u2066-\u2069]/g

const TRIGGER_DISPLAY_PATTERN = /^trigger-\d+$/

const INVALID_ID_MESSAGE = 'IDs must contain only alphanumeric characters, hyphens, underscores, and periods.'

/**
 * SECURITY: Validate an edge endpoint ID (source or target).
 * Allows trigger display IDs (trigger-\d+) which will be mapped later, validates others via isValidId.
 */
function validateEdgeEndpointId(id: string, label: string): void {
  if (!TRIGGER_DISPLAY_PATTERN.test(id) && !isValidId(id)) {
    throw new Error(`Invalid edge ${label} ID: "${id}". ${INVALID_ID_MESSAGE}`)
  }
}

/**
 * SECURITY: Validate all entity IDs in the workflow before building the definition.
 */
function validateEntityIds(activities: Activity[], triggers: Activity[], edges: EdgeConnection[]): void {
  for (const activity of activities) {
    if (!isValidId(activity.id)) {
      throw new Error(`Invalid activity ID: "${activity.id}". ${INVALID_ID_MESSAGE}`)
    }
  }

  for (const trigger of triggers) {
    if (trigger.id !== undefined && !isValidId(trigger.id)) {
      throw new Error(`Invalid trigger ID: "${trigger.id}". ${INVALID_ID_MESSAGE}`)
    }
  }

  for (const edge of edges) {
    validateEdgeEndpointId(edge.source, 'source')
    validateEdgeEndpointId(edge.target, 'target')
  }
}

/**
 * SECURITY: Map a trigger display ID to its real ID.
 * Throws if the trigger lacks an ID or if the display ID wasn't mapped.
 */
function resolveTriggerId(displayId: string, triggers: Activity[], label: string): string {
  const triggerIndex = parseTriggerIndex(displayId)
  if (triggerIndex !== undefined) {
    // SECURITY: Throw immediately if index is valid but trigger doesn't exist
    // (e.g., stale edge referencing a deleted trigger)
    if (!triggers[triggerIndex]) {
      throw new Error(
        `Trigger at index ${triggerIndex} not found (edge ${label} "${displayId}"). ` +
          `The trigger may have been deleted. Display IDs cannot be sent to the API.`
      )
    }
    const trigger = triggers[triggerIndex]
    if (!hasId(trigger)) {
      throw new Error(
        `Trigger at index ${triggerIndex} is missing an ID. ` +
          `Display IDs like "${displayId}" cannot be used in workflow definitions.`
      )
    }
    return trigger.id
  }
  // SECURITY: Catch any display IDs that weren't mapped to real IDs
  // (e.g., if parseTriggerIndex failed due to encoding tricks)
  if (displayId.startsWith('trigger-')) {
    throw new Error(
      `Unmapped trigger display ID in edge ${label}: "${displayId}". Display IDs cannot be sent to the API.`
    )
  }
  return displayId
}

/**
 * SECURITY: Validate name length (max 255 chars).
 */
function validateNameLength(name: string | undefined, entityLabel: string): void {
  if (name && name.length > 255) {
    throw new Error(`${entityLabel} "${name.slice(0, 50)}..." exceeds 255 characters.`)
  }
}

function transformSwitchParametersForBackend(
  parameters: Record<string, unknown> & { cases: Array<{ port: string; label: string; condition: string }> }
): Record<string, unknown> {
  const rest = Object.fromEntries(Object.entries(parameters).filter(([key]) => !key.startsWith('_')))
  return {
    ...rest,
    cases: parameters.cases.map((c) => ({
      ...c,
      condition: transformConditionForBackend(c.condition) ?? c.condition,
    })),
  }
}

/**
 * Transform condition expression from UI format to backend format.
 * Converts `!(...)` syntax to `not (...)` for Python backend compatibility.
 *
 * @param condition - Condition expression string from UI
 * @returns Condition expression string for backend
 * @throws Error if transformation fails (prevents saving malformed expressions)
 */
function transformConditionForBackend(condition: string | undefined): string | undefined {
  if (!condition) return condition

  const parsed = parseExpression(condition)

  // If parsing failed with error, throw to prevent saving malformed expression
  if (parsed.error) {
    throw new Error(`Failed to transform condition expression: ${parsed.error}`)
  }

  if (!parsed.root) return condition

  // Serialize with forBackend: true to convert ! to not
  return serializeExpression(parsed, { forBackend: true })
}

/**
 * Apply all backend-facing transforms to a single node's parameters.
 * Consolidates condition, switch, approval, and converge transforms
 * so both `buildWorkflowDefinition` and version-duplication share one path.
 */
export function transformNodeParameters(type: string, parameters: Record<string, unknown>): Record<string, unknown> {
  let result = parameters

  if ((type === ActivityTypeEnum.CONDITION || type === ActivityTypeEnum.LOOP) && typeof result.condition === 'string') {
    result = {
      ...result,
      condition: transformConditionForBackend(result.condition) ?? result.condition,
    }
  }

  if (type === ActivityTypeEnum.SWITCH && isSwitchCaseArray(result.cases)) {
    result = transformSwitchParametersForBackend(
      result as Record<string, unknown> & { cases: Array<{ port: string; label: string; condition: string }> }
    )
  }

  if (type === ActivityTypeEnum.APPROVAL) {
    result = transformApprovalApprovers(result)
  }

  if (type === ActivityTypeEnum.CONVERGE && 'branches' in result) {
    result = Object.fromEntries(Object.entries(result).filter(([key]) => key !== 'branches'))
  }

  return result
}

/**
 * Build a V2 workflow definition for API submission.
 *
 * Transforms internal workflow representation (React Flow format) to V2 API format:
 * - Maps trigger display IDs (trigger-0, trigger-1) to definition IDs
 * - Converts React Flow handles to V2 port names (loop→iterate, done→complete)
 * - Extracts optional activity inputs using type-safe guards
 *
 * @param workflowName - Workflow name
 * @param workflowDescription - Optional workflow description
 * @param activities - Array of workflow activities (nodes)
 * @param triggers - Array of workflow triggers
 * @param edges - Array of workflow edges (connections)
 * @returns V2 workflow definition ready for API submission
 */
export function buildWorkflowDefinition(
  workflowName: string,
  workflowDescription: string,
  activities: Activity[],
  triggers: Activity[],
  graph: { edges: EdgeConnection[]; nodePositions?: Record<string, { x: number; y: number }> }
) {
  const { edges, nodePositions = {} } = graph
  // SECURITY: Validate and sanitize workflow name and description
  if (!workflowName || workflowName.length > 255) {
    throw new Error('Workflow name is required and must be 255 characters or fewer.')
  }
  if (workflowDescription && workflowDescription.length > 1024) {
    throw new Error('Workflow description must be 1024 characters or fewer.')
  }
  const sanitizedName = workflowName.replace(CONTROL_CHAR_PATTERN, '')
  const sanitizedDescription = workflowDescription?.replace(CONTROL_CHAR_PATTERN, '') || undefined

  validateEntityIds(activities, triggers, edges)

  // SECURITY: Build allowlist of known real IDs for positive validation of edge endpoints.
  // After trigger display IDs are resolved, every edge source/target must match a known
  // activity or trigger ID. This is more robust than negative prefix checks alone.
  const knownIds = new Set<string>()
  for (const a of activities) {
    knownIds.add(a.id)
  }
  for (const t of triggers) {
    if (hasId(t)) {
      knownIds.add(t.id)
    }
  }

  return {
    schema_version: '2.0.0' as const,
    name: sanitizedName,
    description: sanitizedDescription,
    triggers: triggers.map((t) => {
      validateNameLength(t.name, 'Trigger name')
      const sanitizedTriggerName = t.name?.replace(CONTROL_CHAR_PATTERN, '')
      return {
        id: t.id,
        type: t.type,
        ...(sanitizedTriggerName && { name: sanitizedTriggerName }),
        parameters: t.parameters ?? {},
        ...(nodePositions[t.id] ? { position: nodePositions[t.id] } : {}),
      }
    }),
    nodes: activities.map((a) => {
      validateNameLength(a.name, 'Step name')
      const sanitizedNodeName = a.name?.replace(CONTROL_CHAR_PATTERN, '')
      const inputs = hasInputs(a) ? a.inputs : undefined

      const parameters = transformNodeParameters(a.type, a.parameters ?? {})

      return {
        id: a.id,
        type: a.type,
        ...(sanitizedNodeName && { name: sanitizedNodeName }),
        parameters,
        ...(a.settings && { settings: a.settings }),
        ...(inputs && { inputs }),
        ...(a.outputs && { outputs: a.outputs }),
        ...(nodePositions[a.id] ? { position: nodePositions[a.id] } : {}),
      }
    }),
    edges: edges.map((e) => {
      const fromId = resolveTriggerId(e.source, triggers, 'source')
      const toId = resolveTriggerId(e.target, triggers, 'target')

      // SECURITY: Positive validation — resolved IDs must match a known entity
      if (!knownIds.has(fromId)) {
        throw new Error(`Edge source "${fromId}" does not match any known activity or trigger ID.`)
      }
      if (!knownIds.has(toId)) {
        throw new Error(`Edge target "${toId}" does not match any known activity or trigger ID.`)
      }

      const fromPort = handleToV2Port(e.sourceHandle)
      const toPort = e.targetHandle && e.targetHandle !== 'target' ? handleToV2Port(e.targetHandle) : undefined
      return {
        from: fromId,
        to: toId,
        ...(fromPort && { from_port: fromPort }),
        ...(toPort && { to_port: toPort }),
      }
    }),
  }
}
