import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch } from 'react'

import { useNodeKindsQuery } from '../../../hooks/useNodeKindsQuery'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { BuilderAction } from '../builderReducer'
import { blockedStepTypesIn, withoutStepTypes, type CanvasDefinition } from '../stepTypeCanvasGuards'
import { STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP } from '../stepTypePaletteGating'
import { collectCopiedRunActivityIds } from '../utils/executionState/collectCopiedRunActivityIds'
import { parseImportedDefinition } from '../utils/parseImportedDefinition'

export type ExecutionCopyData = {
  executionId: string
  workflowDefinition: Record<string, unknown>
  preserveWorkflow?: boolean
}

type Alert = { title: string; description?: string }

type UseExecutionCopyToEditorOptions = {
  executionCopy: ExecutionCopyData | undefined
  /** Project whose step-type denies apply to the copied steps. */
  projectId: string | null | undefined
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  showSuccess: (alert: Alert) => void
  showError: (alert: Alert) => void
}

/** The copy is waiting for the user to accept leaving out the step types they may not write. */
export type BlockedRunCopy = { labels: string[] }

export type ExecutionCopyToEditor = {
  blockedRunCopy: BlockedRunCopy | null
  confirmBlockedRunCopy: () => void
  cancelBlockedRunCopy: () => void
}

/**
 * How the copy of the run's definition resolves, once it can. `copy-all` and
 * `unavailable` are applied by the effect; `resolved` means a prompt handler
 * already applied or dropped the copy.
 */
type RunCopyDecision = 'copy-all' | 'unavailable' | 'resolved'

function clearExecutionParams() {
  const url = new URL(window.location.href)
  url.searchParams.delete('fromExecution')
  url.searchParams.delete('linkExecution')
  window.history.replaceState({}, '', url.pathname + url.search)
}

function copyRunToEditor(
  executionId: string,
  { workflowDef, edges, nodePositions }: CanvasDefinition,
  omittedLabels: string[],
  { dispatch, markDirty, showSuccess }: Pick<UseExecutionCopyToEditorOptions, 'dispatch' | 'markDirty' | 'showSuccess'>
) {
  useWorkflowStore.getState().replaceWorkflowContent(workflowDef, edges, nodePositions)

  if (workflowDef.name && typeof workflowDef.name === 'string') {
    dispatch({ type: 'SET_WORKFLOW_NAME', payload: workflowDef.name })
  }
  if (workflowDef.description && typeof workflowDef.description === 'string') {
    dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: workflowDef.description })
  }
  markDirty()
  const description = 'The run has been loaded into the editor with pinned runtime data.'
  showSuccess({
    title: 'Run copied to editor',
    description: omittedLabels.length
      ? `${description} Steps of these types were left out: ${omittedLabels.join(', ')}.`
      : description,
  })
  dispatch({
    type: 'SET_MOST_RECENT_EXECUTION',
    payload: { executionId, copiedRunActivityIds: collectCopiedRunActivityIds(workflowDef) },
  })
  clearExecutionParams()
}

/**
 * Load a run into the editor ("copy run to editor"), or link it to the current
 * graph when `preserveWorkflow` is set.
 *
 * Copying the run's definition adds its step types to the canvas, so it waits
 * for the project's step-type verdicts. When some step types are denied, it
 * returns `blockedRunCopy` and copies only once the user confirms leaving those
 * steps out. It fails closed when the verdicts are unavailable.
 */
export function useExecutionCopyToEditor({
  executionCopy,
  projectId,
  dispatch,
  markDirty,
  showSuccess,
  showError,
}: UseExecutionCopyToEditorOptions): ExecutionCopyToEditor {
  const hasAppliedRef = useRef(false)
  const [decision, setDecision] = useState<RunCopyDecision | null>(null)
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow)

  const definition = executionCopy && !executionCopy.preserveWorkflow ? executionCopy.workflowDefinition : undefined
  const { nodeKindByKind, isLoading, isUnavailable } = useNodeKindsQuery(projectId, { enabled: Boolean(definition) })
  const parsed = useMemo(() => (definition ? parseImportedDefinition(definition) : null), [definition])
  const verdictsReady = Boolean(projectId) && !isLoading && !isUnavailable
  const blocked = useMemo(
    () => (parsed && verdictsReady ? blockedStepTypesIn(parsed.workflowDef, nodeKindByKind) : []),
    [parsed, verdictsReady, nodeKindByKind]
  )

  // Settled during render rather than in the effect, so a verdict refetch after
  // the copy (for example a policy change) cannot open the prompt afterwards.
  const canDecide = parsed !== null && Boolean(currentWorkflow) && decision === null
  if (canDecide && isUnavailable) {
    setDecision('unavailable')
  } else if (canDecide && verdictsReady && blocked.length === 0) {
    setDecision('copy-all')
  }

  useEffect(() => {
    if (!executionCopy || hasAppliedRef.current || !currentWorkflow) return

    if (executionCopy.preserveWorkflow) {
      hasAppliedRef.current = true
      // Link execution to current graph — snapshot IDs so newly added nodes get no status
      dispatch({
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: {
          executionId: executionCopy.executionId,
          copiedRunActivityIds: collectCopiedRunActivityIds(currentWorkflow),
        },
      })
      clearExecutionParams()
      return
    }

    if (!parsed) return
    if (decision === 'unavailable') {
      hasAppliedRef.current = true
      showError({ title: 'Cannot copy run to editor', description: STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP })
      clearExecutionParams()
    } else if (decision === 'copy-all') {
      hasAppliedRef.current = true
      copyRunToEditor(executionCopy.executionId, parsed, [], { dispatch, markDirty, showSuccess })
    }
  }, [executionCopy, currentWorkflow, parsed, decision, dispatch, markDirty, showSuccess, showError])

  const isPromptOpen = canDecide && verdictsReady && blocked.length > 0
  const labels = useMemo(() => blocked.map((stepType) => stepType.label), [blocked])

  const confirmBlockedRunCopy = useCallback(() => {
    if (!executionCopy || !parsed || hasAppliedRef.current) return
    hasAppliedRef.current = true
    setDecision('resolved')
    const filtered = withoutStepTypes(
      parsed,
      blocked.map((stepType) => stepType.kind)
    )
    copyRunToEditor(executionCopy.executionId, filtered, labels, { dispatch, markDirty, showSuccess })
  }, [executionCopy, parsed, blocked, labels, dispatch, markDirty, showSuccess])

  const cancelBlockedRunCopy = useCallback(() => {
    if (hasAppliedRef.current) return
    hasAppliedRef.current = true
    setDecision('resolved')
    clearExecutionParams()
  }, [])

  const blockedRunCopy = useMemo(() => (isPromptOpen ? { labels } : null), [isPromptOpen, labels])

  return { blockedRunCopy, confirmBlockedRunCopy, cancelBlockedRunCopy }
}
