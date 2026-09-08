import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import type { ActivityState } from '../../../workflows/execution/types'
import { buildLatestIterationMap } from '../../../workflows/execution/utils/activityState'
import type { EdgeConnection } from '../../types/edge'

import { ACTIVITY_STATUS, TERMINAL_ACTIVITY_STATUSES, isBranchHandle } from './executionHelpers'
import { WorkflowTraversal } from './traversal'

/**
 * Execution state information for an activity.
 */
export type ExecutionState = {
  status: string
  started_at?: string
  completed_at?: string
  error_details?: string
}

function isConvergeSource(edge: { source: string }, activities?: Activity[]): boolean {
  if (activities) {
    const sourceActivity = activities.find((a) => a.id === edge.source)
    if (sourceActivity) {
      return sourceActivity.type === ActivityTypeEnum.CONVERGE
    }
  }
  return edge.source.startsWith('converge-')
}

/**
 * Activity with execution metadata attached.
 */
export type ActivityWithMetadata = Activity & {
  metadata?: {
    __showExecutionBadge?: boolean
    [key: string]: unknown
  }
  __executionState?: ExecutionState
}

/** Optional flags for {@link ExecutionStateEnricher.enrichActivity}. */
export type EnrichActivityOptions = {
  preResolvedNodes?: Set<string>
  /** When set (copy-to-editor), only these IDs may get inferred Skipped status. */
  skipInferenceActivityIds?: ReadonlySet<string>
}

/**
 * Orchestrator for enriching workflow activities with execution state.
 *
 * This class enriches activities with execution status from the backend.
 * For V2 workflows, all nodes (including control flow nodes like condition,
 * loop, converge) have backend-tracked status via ActivityExecution records.
 *
 * @example
 * const enricher = new ExecutionStateEnricher()
 *
 * const enrichedActivity = enricher.enrichActivity(
 *   activity,
 *   activityStates,
 *   edges
 * )
 *
 * const edgeStatus = enricher.determineEdgeStatus(
 *   { source: 'task-1', target: 'task-2' },
 *   activityStates
 * )
 */
function reachableNodes(entryId: string, adjacency: Map<string, string[]>, stopAt?: string): Set<string> {
  const visited = new Set<string>()
  const stack = [entryId]
  while (stack.length > 0) {
    const nodeId = stack.pop()
    if (nodeId === undefined || visited.has(nodeId) || nodeId.startsWith('converge-') || nodeId === stopAt) continue
    visited.add(nodeId)
    for (const child of adjacency.get(nodeId) ?? []) {
      if (!visited.has(child)) stack.push(child)
    }
  }
  return visited
}

function collectLoopBodyGroups(edges: EdgeConnection[]): Map<string, Set<string>> {
  const adjacency = new Map<string, string[]>()
  const loopEntries: Array<{ loopId: string; entryId: string }> = []
  for (const edge of edges) {
    if (edge.sourceHandle === EdgeHandleEnum.LOOP) {
      loopEntries.push({ loopId: edge.source, entryId: edge.target })
    }
    let targets = adjacency.get(edge.source)
    if (!targets) {
      targets = []
      adjacency.set(edge.source, targets)
    }
    targets.push(edge.target)
  }
  const result = new Map<string, Set<string>>()
  for (const { loopId, entryId } of loopEntries) {
    const body = reachableNodes(entryId, adjacency, loopId)
    result.set(loopId, body)
  }
  return result
}

export class ExecutionStateEnricher {
  private cachedIterationMap: Map<string, ActivityState> | null = null
  private cachedIterationMapSource: Map<string, ActivityState> | null = null
  private cachedLoopBodyGroups: ReadonlyMap<string, ReadonlySet<string>> | null = null
  private cachedEdgesSource: EdgeConnection[] | null = null

  private getLoopBodyGroups(edges: EdgeConnection[]): ReadonlyMap<string, ReadonlySet<string>> {
    if (this.cachedEdgesSource === edges && this.cachedLoopBodyGroups) {
      return this.cachedLoopBodyGroups
    }
    this.cachedLoopBodyGroups = collectLoopBodyGroups(edges)
    this.cachedEdgesSource = edges
    return this.cachedLoopBodyGroups
  }

  private getLatestIterationMap(
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[]
  ): Map<string, ActivityState> {
    if (
      this.cachedIterationMapSource === activityStates &&
      this.cachedEdgesSource === edges &&
      this.cachedIterationMap
    ) {
      return this.cachedIterationMap
    }
    this.cachedIterationMap = buildLatestIterationMap(activityStates, this.getLoopBodyGroups(edges))
    this.cachedIterationMapSource = activityStates
    return this.cachedIterationMap
  }

  private resolveActivityState(
    activityId: string,
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[]
  ): ActivityState | undefined {
    return this.getLatestIterationMap(activityStates, edges).get(activityId) ?? activityStates.get(activityId)
  }

  /**
   * Enrich an activity with execution state for visualization.
   *
   * This method:
   * 1. Adds execution badge flag to metadata
   * 2. Adds backend state if available (from activityStates)
   * 3. Marks nodes as skipped when on non-taken branches
   * 4. Returns pending/unknown state if no backend data available
   *
   * All nodes (including control flow) get their status from backend ActivityExecution
   * records. No inference from downstream nodes is performed.
   *
   * @param activity - The activity to enrich
   * @param executionStatus - Current execution status (null if not in execution view)
   * @param activityStates - Map of activity IDs to their execution states from backend
   * @param edges - All edges in the workflow
   * @param options - Optional pre-resolved nodes and copy-to-editor skip allowlist
   * @returns Activity enriched with execution metadata
   */
  enrichActivity(
    activity: Activity,
    executionStatus: string | null | undefined,
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[],
    options?: EnrichActivityOptions
  ): ActivityWithMetadata {
    const { preResolvedNodes, skipInferenceActivityIds } = options ?? {}

    // If not in execution view, return as-is
    if (!executionStatus) {
      return activity as ActivityWithMetadata
    }

    // Step 1: Add direct backend state if available.
    // For loop body nodes, resolveActivityState prefers the latest iteration's
    // state so the canvas shows each iteration's lifecycle rather than the
    // frozen iteration-0 base record.
    const activityState = this.resolveActivityState(activity.id, activityStates, edges)

    // Nodes added after copy-to-editor were never part of the run — no status indicators
    if (!activityState && skipInferenceActivityIds && !skipInferenceActivityIds.has(activity.id)) {
      return activity as ActivityWithMetadata
    }

    // Add execution badge flag to metadata
    const baseMetadata = (activity as ActivityWithMetadata).metadata ?? {}
    let enrichedActivity: ActivityWithMetadata = {
      ...activity,
      metadata: { ...baseMetadata, __showExecutionBadge: true },
    }

    // Mark node if mock data was pinned (test execution pre-resolved node)
    if (preResolvedNodes?.has(activity.id)) {
      enrichedActivity = {
        ...enrichedActivity,
        metadata: {
          ...enrichedActivity.metadata,
          __mockDataPinned: true,
        },
      }
    }

    // Pre-resolved nodes may not have activity records yet (race with backend sync).
    // Force them to SKIPPED if no backend state exists.
    if (!activityState && preResolvedNodes?.has(activity.id)) {
      enrichedActivity = {
        ...enrichedActivity,
        __executionState: { status: 'skipped' as const },
      }
      return enrichedActivity
    }

    if (activityState) {
      enrichedActivity = {
        ...enrichedActivity,
        __executionState: {
          status: activityState.status,
          started_at: activityState.startedAt ?? undefined,
          completed_at: activityState.completedAt ?? undefined,
          error_details: activityState.errorDetails ?? undefined,
        },
      }

      return enrichedActivity
    }

    // Step 2: Check if node should be marked as skipped (allowlist-aware after copy-to-editor)
    if (
      WorkflowTraversal.shouldMarkAsSkipped(activity.id, activityStates, edges, new Set(), skipInferenceActivityIds)
    ) {
      enrichedActivity = {
        ...enrichedActivity,
        __executionState: {
          status: ACTIVITY_STATUS.SKIPPED,
          started_at: undefined,
          completed_at: undefined,
          error_details: undefined,
        },
      }

      return enrichedActivity
    }

    // No backend state and not skipped - return without execution state
    return enrichedActivity
  }

  /**
   * Enrich trigger node data with execution state.
   *
   * Trigger nodes are treated the same as regular activity nodes — their status
   * is read directly from `activityStates` using the trigger's real ID.
   *
   * @param triggerRealId - The trigger's real ID (from workflow definition) for activityStates lookup
   * @param executionStatus - Current execution status (null if not in execution view)
   * @param activityStates - Map of activity states from execution store
   * @returns Trigger data enriched with execution metadata
   */
  enrichTriggerNode<T extends Record<string, unknown>>(
    triggerRealId: string | undefined,
    triggerData: T,
    executionStatus: string | null | undefined,
    activityStates: Map<string, ActivityState>
  ): T & { metadata?: { __showExecutionBadge?: boolean }; __executionState?: ExecutionState } {
    if (!executionStatus) {
      return triggerData
    }

    const triggerState = triggerRealId ? activityStates.get(triggerRealId) : undefined

    const executionHasStarted =
      executionStatus === 'running' ||
      executionStatus === 'paused' ||
      executionStatus === 'completed' ||
      executionStatus === 'failed'

    const status = triggerState?.status ?? (executionHasStarted ? ACTIVITY_STATUS.COMPLETED : ACTIVITY_STATUS.PENDING)

    return {
      ...triggerData,
      metadata: {
        ...(triggerData.metadata as Record<string, unknown> | undefined),
        __showExecutionBadge: true,
      },
      __executionState: {
        status,
        started_at: triggerState?.startedAt ?? undefined,
        completed_at: triggerState?.completedAt ?? undefined,
        error_details: triggerState?.errorDetails ?? undefined,
      },
    }
  }

  /**
   * Determine execution status for an edge.
   *
   * For branching edges (conditional, approval, loop), the edge is "passed" if the target
   * has started, indicating this branch was actually taken during execution.
   *
   * For converge node outgoing edges, the edge is "passed" if the target has started,
   * showing that execution has moved past the converge point.
   *
   * For trigger edges, the edge is "passed" if the trigger is completed (any target started).
   *
   * For regular edges, the edge is "passed" if the source activity reached a terminal status.
   *
   * This determines visual styling:
   * - Passed edges: Solid line (execution traversed this path)
   * - Pending edges: Dashed line (execution hasn't reached this yet)
   *
   * @param edge - The edge to determine status for
   * @param activityStates - Map of activity states from execution store
   * @param activities - Optional list of activities to check source node type
   * @returns 'passed' if edge was traversed, 'pending' otherwise
   */
  private targetHasStarted(
    targetId: string,
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[]
  ): boolean {
    const state = this.resolveActivityState(targetId, activityStates, edges)
    return !!state && state.status !== ACTIVITY_STATUS.PENDING && state.status !== ACTIVITY_STATUS.SKIPPED
  }

  private sourceIsTerminal(
    sourceId: string,
    activityStates: Map<string, ActivityState>,
    edges: EdgeConnection[]
  ): boolean {
    const state = this.resolveActivityState(sourceId, activityStates, edges)
    return !!state && TERMINAL_ACTIVITY_STATUSES.includes(state.status)
  }

  determineEdgeStatus(
    edge: { source: string; target: string; sourceHandle?: string | null },
    activityStates: Map<string, ActivityState>,
    activities: Activity[] | undefined,
    triggerDisplayToRealId: Map<string, string> | undefined,
    edges: EdgeConnection[]
  ): 'passed' | 'pending' {
    const targetStarted = this.targetHasStarted(edge.target, activityStates, edges)

    if (edge.source.startsWith('trigger-')) {
      const triggerRealId = triggerDisplayToRealId?.get(edge.source)
      const sourceCompleted = triggerRealId ? this.sourceIsTerminal(triggerRealId, activityStates, edges) : false
      return sourceCompleted && targetStarted ? 'passed' : 'pending'
    }

    if (isBranchHandle(edge.sourceHandle) || isConvergeSource(edge, activities)) {
      return targetStarted ? 'passed' : 'pending'
    }

    if (this.sourceIsTerminal(edge.source, activityStates, edges)) {
      return targetStarted ? 'passed' : 'pending'
    }

    return 'pending'
  }
}
