/**
 * Activity State Utilities
 *
 * JSON Patch utilities for applying incremental activity updates from WebSocket.
 * Implements RFC 6902 JSON Patch operations (add, replace, remove).
 */

import { ACTIVITY_STATUS } from '../../../builder/utils/executionState/executionHelpers'
import type { ActivityStatus, JsonPatchOperation, ActivityState } from '../types'

// ============================================================================
// JSON Patch Path Parsing
// ============================================================================

/**
 * Parsed JSON Pointer path for activity updates
 */
type ActivityPathInfo = {
  /** Activity ID from the path */
  activityId: string
  /** Field name being updated (e.g., "status", "error_details") */
  field: string
  /** Array index if accessing by index (e.g., /activities/0/status) */
  arrayIndex?: number
}

/**
 * Parse a JSON Pointer path for activity updates
 *
 * Supported formats:
 * - "/activities/{activityId}/status" - Update by activity ID
 * - "/activities/{index}/status" - Update by array index
 * - "/activities/{activityId}/error_details" - Update error
 *
 * @param path - JSON Pointer path
 * @returns Parsed path information
 * @throws Error if path format is invalid
 */
export function parseActivityPath(path: string): ActivityPathInfo {
  // Remove leading slash
  const normalized = path.startsWith('/') ? path.slice(1) : path

  // Split into parts
  const parts = normalized.split('/')

  // Validate format: activities/{id_or_index}/{field}
  if (parts.length !== 3 || parts[0] !== 'activities') {
    throw new Error(`Invalid activity path format: ${path}. Expected /activities/{id}/{field}`)
  }

  const [, idOrIndex, field] = parts

  if (!idOrIndex || !field) {
    throw new Error(`Invalid activity path: ${path}. Missing activity ID or field`)
  }

  const isArrayIndex = /^(0|[1-9]\d*)$/.test(idOrIndex)
  const arrayIndex = isArrayIndex ? Number(idOrIndex) : undefined

  return {
    activityId: idOrIndex,
    field,
    arrayIndex,
  }
}

// ============================================================================
// JSON Patch Operations
// ============================================================================

function applyFieldUpdate(activity: ActivityState, field: string, value: unknown): ActivityState {
  const updated = { ...activity }
  switch (field) {
    case 'status':
      updated.status = value as ActivityStatus
      break
    case 'error_details':
      updated.errorDetails = value as string | null
      break
    case 'started_at':
      updated.startedAt = value as string | null
      break
    case 'completed_at':
      updated.completedAt = value as string | null
      break
    case 'output_data':
      updated.outputData = value as Record<string, unknown> | null
      break
    case 'iteration':
      updated.iteration = value as number | null
      break
    default:
      throw new Error(`Unsupported field for activity update: ${field}`)
  }
  return updated
}

function resolveActivityId(
  activityId: string,
  arrayIndex: number | undefined,
  activityArray?: ActivityState[]
): string {
  if (arrayIndex === undefined) return activityId
  if (!activityArray) {
    throw new Error(`Cannot resolve array index ${arrayIndex} without activityArray`)
  }
  const activity = activityArray[arrayIndex]
  if (!activity) {
    throw new Error(`Activity not found at index ${arrayIndex}`)
  }
  return activity.activityId
}

/**
 * Apply a single JSON Patch operation to activity state
 *
 * @param activities - Map of activity states (mutated in place)
 * @param operation - JSON Patch operation to apply
 * @param activityArray - Optional array for index-based lookups
 * @throws Error if operation is invalid or path doesn't exist
 */
function applyAddOperation(
  activities: Map<string, ActivityState>,
  resolvedId: string,
  field: string,
  value: unknown,
  existing: ActivityState | undefined
): void {
  if (value === undefined) {
    throw new Error(`Operation 'add' requires a value`)
  }

  if (!existing) {
    if (field !== 'status') {
      throw new Error(`Cannot create activity with field '${field}'. 'status' is required first.`)
    }
    activities.set(resolvedId, { activityId: resolvedId, status: value as ActivityStatus })
    return
  }

  activities.set(resolvedId, applyFieldUpdate(existing, field, value))
}

function applyReplaceOperation(
  activities: Map<string, ActivityState>,
  resolvedId: string,
  field: string,
  value: unknown,
  existing: ActivityState | undefined
): void {
  if (value === undefined) {
    throw new Error(`Operation 'replace' requires a value`)
  }
  if (!existing) {
    // Only status replace may create an activity (mirrors applyAddOperation).
    // Other fields arriving first would otherwise invent a synthetic 'pending'.
    if (field !== 'status') {
      throw new Error(`Cannot replace field '${field}' on non-existent activity '${resolvedId}'`)
    }
    activities.set(resolvedId, { activityId: resolvedId, status: value as ActivityStatus })
    return
  }
  activities.set(resolvedId, applyFieldUpdate(existing, field, value))
}

function applyRemoveOperation(
  activities: Map<string, ActivityState>,
  resolvedId: string,
  field: string,
  existing: ActivityState | undefined
): void {
  if (field !== 'error_details') {
    throw new Error(`Cannot remove field '${field}' from activity. Only 'error_details' can be removed.`)
  }
  if (!existing) {
    throw new Error(`Cannot remove field '${field}' from non-existent activity '${resolvedId}'`)
  }
  activities.set(resolvedId, { ...existing, errorDetails: null })
}

/**
 * Handle "add" op with path "/activities/-" — append a full activity record.
 * The value is a complete ActivityData object from the backend.
 */
function applyAppendOperation(activities: Map<string, ActivityState>, value: unknown): void {
  if (!value || typeof value !== 'object') {
    throw new Error(`Operation 'add' at /activities/- requires an activity object as value`)
  }
  const data = value as Record<string, unknown>
  const activityId = data.activity_id
  if (typeof activityId !== 'string' || !activityId) {
    throw new Error(`Activity object missing activity_id`)
  }
  activities.set(activityId, {
    activityId,
    status: typeof data.status === 'string' ? (data.status as ActivityStatus) : ACTIVITY_STATUS.PENDING,
    errorDetails: typeof data.error_details === 'string' ? data.error_details : null,
    outputData:
      data.output_data != null && typeof data.output_data === 'object'
        ? (data.output_data as Record<string, unknown>)
        : null,
    startedAt: typeof data.started_at === 'string' ? data.started_at : null,
    completedAt: typeof data.completed_at === 'string' ? data.completed_at : null,
    iteration: typeof data.iteration === 'number' ? data.iteration : null,
  })
}

export function applyOperation(
  activities: Map<string, ActivityState>,
  operation: JsonPatchOperation,
  activityArray?: ActivityState[]
): void {
  const { op, path, value } = operation

  // Handle append-to-array: "add" with path "/activities/-"
  if (op === 'add' && path === '/activities/-') {
    applyAppendOperation(activities, value)
    return
  }

  const { activityId, field, arrayIndex } = parseActivityPath(path)
  const resolvedId = resolveActivityId(activityId, arrayIndex, activityArray)
  const existing = activities.get(resolvedId)

  switch (op) {
    case 'add':
      applyAddOperation(activities, resolvedId, field, value, existing)
      break
    case 'replace':
      applyReplaceOperation(activities, resolvedId, field, value, existing)
      break
    case 'remove':
      applyRemoveOperation(activities, resolvedId, field, existing)
      break
    case 'move':
    case 'copy':
    case 'test':
      throw new Error(`Operation '${op}' is not supported for activity updates`)

    default: {
      const _exhaustive: never = op
      throw new Error(`Unknown operation: ${String(_exhaustive)}`)
    }
  }
}

/**
 * Apply multiple JSON Patch operations to activity state
 *
 * Operations are applied sequentially. If any operation fails,
 * an error is thrown and the state may be partially updated.
 *
 * @param activities - Map of activity states (mutated in place)
 * @param operations - Array of JSON Patch operations
 * @param activityArray - Optional array for index-based lookups
 * @throws Error if any operation is invalid
 */
export function applyJsonPatch(
  activities: Map<string, ActivityState>,
  operations: JsonPatchOperation[],
  activityArray?: ActivityState[]
): void {
  for (const operation of operations) {
    try {
      applyOperation(activities, operation, activityArray)
    } catch (error) {
      // Re-throw with context
      const message = error instanceof Error ? error.message : String(error)
      throw new Error(`Failed to apply operation ${operation.op} at ${operation.path}: ${message}`, {
        cause: error,
      })
    }
  }
}

/** Approval audit data extracted from activity output_data. Fields match the approval resultSchema in the backend. */
export type ApprovalAudit = {
  decision: string
  decidedBy: string
  decidedAt: string
  decisionNotes: string | null
}

/**
 * Extract approval audit info from activity output data.
 *
 * This uses a heuristic: if output_data contains `decision` and `decided_by`,
 * we treat it as approval audit data. This avoids requiring the node type
 * to be passed through the WebSocket patch path.
 */
export function extractApprovalAudit(outputData: Record<string, unknown> | null | undefined): ApprovalAudit | null {
  if (!outputData) return null

  const decision = outputData.decision
  const decidedBy = outputData.decided_by
  const decidedAt = outputData.decided_at

  if (typeof decision !== 'string' || typeof decidedBy !== 'string' || typeof decidedAt !== 'string') {
    return null
  }

  return {
    decision,
    decidedBy,
    decidedAt,
    decisionNotes: typeof outputData.decision_notes === 'string' ? outputData.decision_notes : null,
  }
}

// ============================================================================
// Activity State Helpers
// ============================================================================

/**
 * Convert API ActivityData array to Map for fast lookup
 *
 * @param activities - Array of activity data from REST API
 * @returns Map of activity states keyed by activity_id
 */
export function buildActivityStateMap(
  activities: Array<{
    activity_id: string
    status: ActivityStatus
    error_details?: string | null
    output_data?: Record<string, unknown> | null
    started_at?: string | null
    completed_at?: string | null
    iteration?: number | null
  }>
): Map<string, ActivityState> {
  const map = new Map<string, ActivityState>()

  for (const activity of activities) {
    map.set(activity.activity_id, {
      activityId: activity.activity_id,
      status: activity.status,
      errorDetails: activity.error_details,
      outputData: activity.output_data,
      startedAt: activity.started_at,
      completedAt: activity.completed_at,
      iteration: activity.iteration,
    })
  }

  return map
}

// Wire-format separator for per-iteration composite keys (e.g. "body-1#iter-2").
// Mirrored in backend: src/syntara/workflows/workflow_engine/services/activity_sync_service.py
const COMPOSITE_ITER_SEP = '#iter-'

/**
 * Parse a composite activity key into base node ID and iteration number.
 *
 * Composite keys use the format ``{nodeId}#iter-{N}`` for per-iteration records.
 * Non-composite keys return the original ID with ``iteration: undefined``.
 */
export function parseCompositeKey(activityId: string): { baseId: string; iteration?: number } {
  const hashIdx = activityId.indexOf(COMPOSITE_ITER_SEP)
  if (hashIdx === -1) return { baseId: activityId }
  const parsed = Number(activityId.slice(hashIdx + COMPOSITE_ITER_SEP.length))
  return {
    baseId: activityId.slice(0, hashIdx),
    iteration: Number.isFinite(parsed) ? parsed : undefined,
  }
}

const TERMINAL_STATUSES: Set<string> = new Set([
  ACTIVITY_STATUS.COMPLETED,
  ACTIVITY_STATUS.FAILED,
  ACTIVITY_STATUS.CANCELLED,
  ACTIVITY_STATUS.SKIPPED,
])

function makePendingState(nodeId: string, iteration: number): ActivityState {
  return {
    activityId: nodeId,
    status: ACTIVITY_STATUS.PENDING,
    startedAt: null,
    completedAt: null,
    errorDetails: null,
    iteration,
  }
}

/**
 * Scan composite keys to find each base ID's highest-iteration record.
 */
function collectLatestIterations(activityStates: Map<string, ActivityState>) {
  const latest = new Map<string, { iteration: number; state: ActivityState }>()
  for (const [key, state] of activityStates) {
    const { baseId, iteration } = parseCompositeKey(key)
    if (iteration === undefined) continue
    const prev = latest.get(baseId)
    if (!prev || iteration > prev.iteration) {
      latest.set(baseId, { iteration, state })
    }
  }
  return latest
}

function buildNodeToLoopLookup(loopBodyGroups: ReadonlyMap<string, ReadonlySet<string>>): Map<string, string> {
  const nodeToLoop = new Map<string, string>()
  for (const [loopId, bodyIds] of loopBodyGroups) {
    for (const nodeId of bodyIds) {
      nodeToLoop.set(nodeId, loopId)
    }
  }
  return nodeToLoop
}

function computeMaxIterations(
  latest: Map<string, { iteration: number; state: ActivityState }>,
  nodeToLoop: Map<string, string>
) {
  const perLoop = new Map<string, number>()
  let global = 0
  for (const [baseId, { iteration }] of latest) {
    if (iteration > global) global = iteration
    const loopId = nodeToLoop.get(baseId)
    if (loopId === undefined) continue
    const current = perLoop.get(loopId) ?? 0
    if (iteration > current) perLoop.set(loopId, iteration)
  }
  return { perLoop, global }
}

function getEffectiveMax(
  loopId: string | undefined,
  iteration: number,
  maxIter: { perLoop: Map<string, number>; global: number },
  hasGroups: boolean
): number {
  if (loopId !== undefined) return maxIter.perLoop.get(loopId) ?? 0
  if (hasGroups) return iteration
  return maxIter.global
}

function resetStaleBaseRecords(
  result: Map<string, ActivityState>,
  activityStates: Map<string, ActivityState>,
  loopBodyGroups: ReadonlyMap<string, ReadonlySet<string>>,
  maxIterPerLoop: Map<string, number>
): void {
  for (const [loopId, bodyIds] of loopBodyGroups) {
    const groupMax = maxIterPerLoop.get(loopId) ?? 0
    if (groupMax <= 0) continue
    for (const nodeId of bodyIds) {
      if (result.has(nodeId)) continue
      const base = activityStates.get(nodeId)
      if (base && TERMINAL_STATUSES.has(base.status)) {
        result.set(nodeId, makePendingState(nodeId, groupMax))
      }
    }
  }
}

/**
 * Build a map from base node ID → latest iteration's {@link ActivityState}.
 *
 * Used by the canvas enricher so that nodes display the most recent
 * iteration's lifecycle (pending → running → completed) rather than the
 * frozen iteration-0 base record.  Only entries with composite keys
 * (``{nodeId}#iter-{N}``) contribute; activities without iterations are
 * ignored.
 *
 * When a new iteration begins, body nodes are scheduled sequentially — the
 * first node gets its ``#iter-N`` record before siblings do.  To avoid
 * showing stale terminal status for siblings that haven't been scheduled yet,
 * any node whose latest iteration is behind the max iteration across all
 * body nodes *within the same loop* is returned as PENDING.
 *
 * For the first → second iteration transition, body nodes that ran only in
 * iteration 0 have no composite keys (the backend uses the base record for
 * iter-0).  Pass ``loopBodyGroups`` so these nodes are also reset to PENDING
 * when a sibling has advanced to a higher iteration.
 *
 * @param loopBodyGroups - Map from loop node ID to the set of body node IDs
 *   belonging to that loop.  When provided, max iteration is computed
 *   per-loop so independent loops don't interfere with each other.
 */
export function buildLatestIterationMap(
  activityStates: Map<string, ActivityState>,
  loopBodyGroups?: ReadonlyMap<string, ReadonlySet<string>>
): Map<string, ActivityState> {
  const latest = collectLatestIterations(activityStates)
  const nodeToLoop = loopBodyGroups ? buildNodeToLoopLookup(loopBodyGroups) : new Map<string, string>()
  const maxIter = computeMaxIterations(latest, nodeToLoop)

  const result = new Map<string, ActivityState>()
  for (const [baseId, { iteration, state }] of latest) {
    const effectiveMax = getEffectiveMax(nodeToLoop.get(baseId), iteration, maxIter, !!loopBodyGroups)
    result.set(baseId, iteration < effectiveMax ? makePendingState(baseId, effectiveMax) : state)
  }

  if (loopBodyGroups) {
    resetStaleBaseRecords(result, activityStates, loopBodyGroups, maxIter.perLoop)
  }

  return result
}

/**
 * Extract activity states and errors from activity map
 *
 * @param activities - Map of activity states
 * @returns Tuple of [activityStates, activityErrors]
 */
export function extractActivityMaps(
  activities: Map<string, ActivityState>
): [Map<string, ActivityStatus>, Map<string, string>] {
  const activityStates = new Map<string, ActivityStatus>()
  const activityErrors = new Map<string, string>()

  for (const [activityId, activity] of activities) {
    activityStates.set(activityId, activity.status)
    if (activity.errorDetails) {
      activityErrors.set(activityId, activity.errorDetails)
    }
  }

  return [activityStates, activityErrors]
}
