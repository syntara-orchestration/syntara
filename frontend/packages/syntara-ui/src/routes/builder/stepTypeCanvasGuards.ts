import { useCallback } from 'react'

import { useNodeKindsQuery, type NodeKind } from '../../hooks/useNodeKindsQuery'
import { useAlerts } from '../../providers/alerts/AlertContext'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import {
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
  stepTypeBlockedMessage,
} from './stepTypePaletteGating'
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
 * Why the verdicts cannot be trusted yet, or null when they can.
 *
 * Denies are evaluated per project, so without one the guards fail closed like
 * the add-step panel does. They also fail closed until the verdicts arrive,
 * not only when the request fails.
 */
export function verdictsFailClosedMessage(projectId: string | null | undefined, isPending: boolean): string | null {
  if (!projectId) return STEP_TYPE_NO_PROJECT_TOOLTIP
  return isPending ? STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP : null
}

type UseStepTypeCanvasGuardsParams = {
  /** Project whose step-type denies apply (the builder's project, saved or not). */
  projectId: string | null | undefined
  currentWorkflow: Pick<WorkflowDefinition, 'workflow'> | null
  duplicateActivity: (nodeId: string) => void
  /** Called after a duplicate is refused, for example to drop a pending node position. */
  onDuplicateRefused?: () => void
}

/**
 * Refuse duplicating a step, or pasting an import onto the canvas, when that
 * would add a step type the caller may not author in the builder's project.
 *
 * Reads the cached `GET /node_kinds` verdicts shared with the add-step panel
 * and fails closed while they are loading, unavailable, or no project is
 * selected. The server still rejects the save; this is UX only.
 */
export function useStepTypeCanvasGuards({
  projectId,
  currentWorkflow,
  duplicateActivity,
  onDuplicateRefused,
}: UseStepTypeCanvasGuardsParams) {
  const { showError } = useAlerts()
  const { nodeKindByKind, isLoading, isUnavailable } = useNodeKindsQuery(projectId)
  const failClosedMessage = verdictsFailClosedMessage(projectId, isLoading || isUnavailable)

  const guardedDuplicateActivity = useCallback(
    (nodeId: string) => {
      const activity = currentWorkflow?.workflow.activities?.find((a) => a.id === nodeId)
      const refusal = activity?.type ? stepTypeRefusal(activity.type, { nodeKindByKind, failClosedMessage }) : null
      if (refusal) {
        onDuplicateRefused?.()
        showError({ title: 'Cannot duplicate step', description: refusal })
        return
      }
      duplicateActivity(nodeId)
    },
    [currentWorkflow, nodeKindByKind, failClosedMessage, duplicateActivity, onDuplicateRefused, showError]
  )

  const getImportRefusal = useCallback(
    (data: PendingImportData) => importRefusal(data, { nodeKindByKind, failClosedMessage }),
    [nodeKindByKind, failClosedMessage]
  )

  return { duplicateActivity: guardedDuplicateActivity, getImportRefusal }
}
