import { useCallback } from 'react'

import { useNodeKindsQuery, type BlockedStepType, type NodeKind } from '../../hooks/useNodeKindsQuery'
import { useAlerts } from '../../providers/alerts/AlertContext'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import {
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_LOADING_MESSAGE,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
  stepTypeBlockedMessage,
} from './stepTypePaletteGating'
import type { EdgeConnection } from './types/edge'
import type { PendingImportData } from './useWorkflowImportExport'

/** Step-type verdicts for the builder's project, as read from `GET /node_kinds`. */
export type StepTypeVerdicts = {
  nodeKindByKind: ReadonlyMap<string, NodeKind>
  /**
   * Why every step type must be refused right now (no project, verdicts still
   * loading, endpoint unavailable), or null when the verdicts can be trusted.
   */
  failClosedMessage: string | null
}

/**
 * Refusal message for adding one step of `kind` to the canvas, or null to allow it.
 *
 * Uses the same wording as the add-step panel tooltip. Kinds the endpoint does
 * not report have no verdict and are allowed, as in the panel.
 */
export function stepTypeRefusal(kind: string, verdicts: StepTypeVerdicts): string | null {
  if (verdicts.failClosedMessage) return verdicts.failClosedMessage
  const verdict = verdicts.nodeKindByKind.get(kind)
  if (!verdict || verdict.can_write) return null
  return verdict.blocked_by ? stepTypeBlockedMessage(verdict.blocked_by) : STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
}

/** Refusal message for pasting `data` onto the canvas, or null to allow it. */
export function importRefusal(data: PendingImportData, verdicts: StepTypeVerdicts): string | null {
  if (verdicts.failClosedMessage) return verdicts.failClosedMessage
  const kinds = new Set<string>()
  for (const activity of data.workflowDef.workflow.activities ?? []) {
    if (activity.type) kinds.add(activity.type)
  }
  for (const trigger of data.workflowDef.triggers ?? []) {
    if (trigger.type) kinds.add(trigger.type)
  }
  for (const kind of kinds) {
    const refusal = stepTypeRefusal(kind, verdicts)
    if (refusal) return refusal
  }
  return null
}

/**
 * Step types in `workflowDef` the caller may not write, unique and in the order
 * they first appear (activities, then triggers).
 *
 * The label is the step type's own name, never the policy that denies it.
 * Kinds with no verdict are allowed, as in `stepTypeRefusal`.
 */
export function blockedStepTypesIn(
  workflowDef: Pick<WorkflowDefinition, 'workflow' | 'triggers'>,
  nodeKindByKind: ReadonlyMap<string, NodeKind>
): BlockedStepType[] {
  const blocked = new Map<string, BlockedStepType>()
  for (const step of [...workflowDef.workflow.activities, ...(workflowDef.triggers ?? [])]) {
    const verdict = step.type ? nodeKindByKind.get(step.type) : undefined
    if (!verdict || verdict.can_write || blocked.has(verdict.kind)) continue
    blocked.set(verdict.kind, { kind: verdict.kind, label: verdict.blocked_by?.label ?? verdict.kind })
  }
  return [...blocked.values()]
}

/** A workflow definition as laid out on the canvas: steps, edges and node positions. */
export type CanvasDefinition = {
  workflowDef: WorkflowDefinition
  edges: EdgeConnection[]
  nodePositions: Record<string, { x: number; y: number }>
}

/**
 * `parsed` without the activities and triggers of the given step types, the
 * edges touching them and their node positions. Does not mutate `parsed`.
 */
export function withoutStepTypes(parsed: CanvasDefinition, kinds: Iterable<string>): CanvasDefinition {
  const removedKinds = new Set(kinds)
  const removedIds = new Set<string>()
  const keep = (step: { id?: string; type?: string }): boolean => {
    if (!step.type || !removedKinds.has(step.type)) return true
    if (step.id) removedIds.add(step.id)
    return false
  }

  const { workflowDef } = parsed
  const activities = workflowDef.workflow.activities.filter(keep)
  const triggers = workflowDef.triggers?.filter(keep)
  return {
    workflowDef: { ...workflowDef, workflow: { ...workflowDef.workflow, activities }, triggers },
    edges: parsed.edges.filter((edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target)),
    nodePositions: Object.fromEntries(Object.entries(parsed.nodePositions).filter(([id]) => !removedIds.has(id))),
  }
}

/**
 * Why the verdicts cannot be trusted yet, or null when they can.
 *
 * Denies are evaluated per project, so without one the guards fail closed like
 * the add-step panel does. They also fail closed until the verdicts arrive,
 * not only when the request fails, with a message that says which it is.
 */
export function verdictsFailClosedMessage(
  projectId: string | null | undefined,
  isLoading: boolean,
  isUnavailable: boolean
): string | null {
  if (!projectId) return STEP_TYPE_NO_PROJECT_TOOLTIP
  if (isLoading) return STEP_TYPE_PERMISSIONS_LOADING_MESSAGE
  return isUnavailable ? STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP : null
}

type UseStepTypeCanvasGuardsParams = {
  /** Project whose step-type denies apply (the builder's project, saved or not). */
  projectId: string | null | undefined
}

/**
 * Refuse duplicating a step, or pasting an import onto the canvas, when that
 * would add a step type the caller may not author in the builder's project.
 *
 * Reads the cached `GET /node_kinds` verdicts shared with the add-step panel
 * and fails closed while they are loading, unavailable, or no project is
 * selected. The server still rejects the save; this is UX only.
 */
export function useStepTypeCanvasGuards({ projectId }: UseStepTypeCanvasGuardsParams) {
  const { showError } = useAlerts()
  const { nodeKindByKind, isLoading, isUnavailable } = useNodeKindsQuery(projectId)
  const failClosedMessage = verdictsFailClosedMessage(projectId, isLoading, isUnavailable)

  // Checked before the duplicate starts, so a refusal changes nothing in the
  // builder. Reads the workflow from the store to keep a stable identity
  // across edits: the step menu of every canvas node depends on it.
  const canDuplicateActivity = useCallback(
    (nodeId: string): boolean => {
      const activities = useWorkflowStore.getState().currentWorkflow?.workflow.activities
      const activity = activities?.find((a) => a.id === nodeId)
      const refusal = activity?.type ? stepTypeRefusal(activity.type, { nodeKindByKind, failClosedMessage }) : null
      if (!refusal) return true
      showError({ title: 'Cannot duplicate step', description: refusal })
      return false
    },
    [nodeKindByKind, failClosedMessage, showError]
  )

  const getImportRefusal = useCallback(
    (data: PendingImportData) => importRefusal(data, { nodeKindByKind, failClosedMessage }),
    [nodeKindByKind, failClosedMessage]
  )

  return { canDuplicateActivity, getImportRefusal }
}
