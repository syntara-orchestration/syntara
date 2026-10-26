import { Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import { useEffect, useEffectEvent, useId, useLayoutEffect, useRef, useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { detachPromise } from '../../utils/detachPromise'
import type { WorkflowDefShape } from '../builder/ExecutionDetailsPanel'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import {
  canConfirmRetryFromFailure,
  eligibleRetryPointIds,
  getRetryPlanPoints,
  selectedRetryPointId,
  type RetryFromFailurePreview,
} from './retryFromFailure'
import { RetryFromFailureInputOverrides } from './RetryFromFailureInputOverrides'
import styles from './RetryFromFailureSidePanel.module.css'
import { HowRetryWorks, RetryFooter, RetryPlan, type RetryScopeMode } from './RetryFromFailureSidePanelParts'
import { getRetryInputOverrideTargets, type ExecutionActivity } from './retryInputOverrides'

type RetryFromFailureSidePanelProps = Readonly<{
  executionId: string
  activities?: ExecutionActivity[]
  activityNameMap: ReadonlyMap<string, string>
  activityTypeMap: ReadonlyMap<string, string>
  workflowDefinition?: WorkflowDefShape | null
  selectedNodeId?: string | null
  onRetryPreviewPointIdsChange?: (pointIds: string[]) => void
  onClose: () => void
}>

type RetryPreviewState = ReturnType<typeof useRetryFromFailurePreview>

/** Full in-context retry review shown beside the source execution. */
export function RetryFromFailureSidePanel({
  executionId,
  activities = [],
  activityNameMap,
  activityTypeMap,
  workflowDefinition,
  selectedNodeId,
  onRetryPreviewPointIdsChange,
  onClose,
}: RetryFromFailureSidePanelProps) {
  const navigate = useNavigate()
  const scopeId = useId()
  const panelRef = useRef<HTMLElement | null>(null)
  const [scopeModeOverride, setScopeModeOverride] = useState<RetryScopeMode>()
  const [checkedRetryPointIds, setCheckedRetryPointIds] = useState<string[]>([])
  const [shouldAnnounceRetryPlan, setShouldAnnounceRetryPlan] = useState(false)
  const [inputOverrideDrafts, setInputOverrideDrafts] = useState<Record<string, string>>({})
  const [inputParameterOverrides, setInputParameterOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [inputOverrideErrors, setInputOverrideErrors] = useState<Record<string, string>>({})

  const defaultPreviewQuery = useRetryFromFailurePreview({ executionId, enabled: true })
  const defaultPoints = getRetryPlanPoints(defaultPreviewQuery.preview, activityNameMap, activityTypeMap)
  const selectedCanvasPointId = selectedRetryPointId(selectedNodeId, defaultPreviewQuery.preview)
  const scopeMode = scopeModeOverride ?? (selectedCanvasPointId ? 'selected' : 'all')
  const selectedPointIds = getSelectedPointIds(scopeModeOverride, selectedCanvasPointId, checkedRetryPointIds)
  const autoIncludedPointIds = new Set(defaultPreviewQuery.preview?.auto_included_node_ids ?? [])
  const selectablePoints = defaultPoints.filter((point) => !autoIncludedPointIds.has(point.id))
  const selectedPointIdSet = new Set(selectedPointIds)
  const requestedRetryPointIds = selectablePoints
    .filter((point) => selectedPointIdSet.has(point.id))
    .map((point) => point.id)

  const selectedPreviewQuery = useRetryFromFailurePreview({
    executionId,
    retryPointIds: requestedRetryPointIds,
    enabled: scopeMode === 'selected' && requestedRetryPointIds.length > 0,
  })
  const activePreview = scopeMode === 'all' ? defaultPreviewQuery.preview : selectedPreviewQuery.preview
  const activeIsLoading = getActivePreviewLoading(
    scopeMode,
    requestedRetryPointIds,
    defaultPreviewQuery,
    selectedPreviewQuery
  )
  const activeIsError = scopeMode === 'all' ? defaultPreviewQuery.isError : selectedPreviewQuery.isError
  const visiblePoints = getRetryPlanPoints(activePreview, activityNameMap, activityTypeMap)
  const retryPlanAnnouncement = getCurrentRetryPlanAnnouncement({
    shouldAnnounce: shouldAnnounceRetryPlan,
    scopeMode,
    selectedCount: requestedRetryPointIds.length,
    isLoading: activeIsLoading,
    preview: activePreview,
    isError: activeIsError,
    visiblePoints,
  })

  useLayoutEffect(() => {
    panelRef.current?.focus()
  }, [])

  const inputOverridePointIds =
    scopeMode === 'all'
      ? eligibleRetryPointIds(defaultPreviewQuery.preview).filter(
          (pointId) => !defaultPreviewQuery.preview?.auto_included_node_ids?.includes(pointId)
        )
      : requestedRetryPointIds
  const inputOverrideTargets = activePreview?.eligible
    ? getRetryInputOverrideTargets(inputOverridePointIds, workflowDefinition, activityNameMap, activities)
    : []
  const hasInvalidInputOverride = inputOverrideTargets.some((target) => Boolean(inputOverrideErrors[target.id]))
  const requestedRetryPointIdsKey = requestedRetryPointIds.join('\u0000')
  const retryPreviewPointIdsKey = getRetryPreviewPointIdsKey({
    scopeMode,
    defaultPreview: defaultPreviewQuery.preview,
    requestedPointIdsKey: requestedRetryPointIdsKey,
    isLoading: activeIsLoading,
    activePreview,
  })
  const notifyRetryPreviewPointIdsChange = useEffectEvent((pointIds: string[]) => {
    onRetryPreviewPointIdsChange?.(pointIds)
  })

  useEffect(() => {
    notifyRetryPreviewPointIdsChange(retryPreviewPointIdsKey ? retryPreviewPointIdsKey.split('\u0000') : [])
  }, [retryPreviewPointIdsKey])

  const retry = useRetryFromFailure({
    executionId,
    onSuccess: (newExecutionId) => {
      onClose()
      detachPromise(navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newExecutionId) }))
    },
  })
  const isRetryDisabled =
    !canConfirmRetryFromFailure(activePreview, activeIsLoading, activeIsError) ||
    (scopeMode === 'selected' && requestedRetryPointIds.length === 0) ||
    hasInvalidInputOverride ||
    retry.isPending

  const updateInputOverrideDraft = (
    nodeId: string,
    value: string,
    parsed: Record<string, unknown> | undefined,
    error: string | undefined
  ) => {
    setInputOverrideDrafts((current) => ({ ...current, [nodeId]: value }))
    setInputOverrideErrors((current) => {
      if (error) return { ...current, [nodeId]: error }
      const next = { ...current }
      delete next[nodeId]
      return next
    })
    setInputParameterOverrides((current) => {
      if (parsed) return { ...current, [nodeId]: parsed }
      const next = { ...current }
      delete next[nodeId]
      return next
    })
  }

  const submitInputParameterOverrides = Object.fromEntries(
    inputOverrideTargets.flatMap((target) => {
      const overrides = inputParameterOverrides[target.id]
      return overrides && Object.keys(overrides).length > 0 ? [[target.id, overrides] as const] : []
    })
  )

  const setAllRetryPoints = () => {
    setShouldAnnounceRetryPlan(true)
    setScopeModeOverride('all')
    setCheckedRetryPointIds([])
  }

  const chooseRetryPoints = () => {
    setShouldAnnounceRetryPlan(true)
    setScopeModeOverride('selected')
    setCheckedRetryPointIds(selectedCanvasPointId ? [selectedCanvasPointId] : [])
  }

  const updateRetryPoint = (pointId: string, isChecked: boolean) => {
    setShouldAnnounceRetryPlan(true)
    setScopeModeOverride('selected')
    setCheckedRetryPointIds((currentIds) => {
      const currentSelection = getSelectedPointIds(scopeModeOverride, selectedCanvasPointId, currentIds)
      if (isChecked) return [...new Set([...currentSelection, pointId])]
      return currentSelection.filter((id) => id !== pointId)
    })
  }

  const footer = (
    <RetryFooter
      onRetry={() =>
        retry.handleRetry(scopeMode === 'all' ? undefined : requestedRetryPointIds, submitInputParameterOverrides)
      }
      onCancel={onClose}
      isRetryDisabled={isRetryDisabled}
      isRetryPending={retry.isPending}
    />
  )

  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      className={styles.panel}
      aria-label="Retry run from failure review"
      data-testid="retry-from-failure-panel"
    >
      <SynPanel hasNoPadding isFullHeight isScrollable footer={footer}>
        <div className={styles.panelInner}>
          <Stack className={styles.panelStack}>
            <StackItem className={styles.headerPadding}>
              <SidePanelHeader title="Retry run from failure" onClose={onClose} closeAriaLabel="Close retry review" />
            </StackItem>
            <StackItem isFilled className={styles.bodyPadding}>
              <Stack hasGutter>
                <StackItem>
                  <HowRetryWorks />
                </StackItem>
                <StackItem>
                  <Title className={styles.sectionTitle} headingLevel="h3" size={TitleSizes.md}>
                    Retry plan
                  </Title>
                  <RetryPlan
                    defaultPreview={defaultPreviewQuery.preview}
                    defaultIsLoading={defaultPreviewQuery.isLoading}
                    defaultIsError={defaultPreviewQuery.isError}
                    activePreview={activePreview}
                    activeIsLoading={activeIsLoading}
                    activeIsError={activeIsError}
                    defaultPoints={defaultPoints}
                    selectablePoints={selectablePoints}
                    visiblePoints={visiblePoints}
                    requestedRetryPointIds={requestedRetryPointIds}
                    scopeMode={scopeMode}
                    scopeId={scopeId}
                    isRetryPending={retry.isPending}
                    onSelectAll={setAllRetryPoints}
                    onChoosePoints={chooseRetryPoints}
                    onUpdatePoint={updateRetryPoint}
                  />
                  <div className="pf-v6-u-screen-reader" role="status" aria-live="polite" aria-atomic="true">
                    {retryPlanAnnouncement}
                  </div>
                </StackItem>
                {activePreview?.eligible && (
                  <StackItem>
                    <RetryFromFailureInputOverrides
                      executionId={executionId}
                      targets={inputOverrideTargets}
                      workflowDefinitionAvailable={workflowDefinition !== undefined && workflowDefinition !== null}
                      isDisabled={retry.isPending}
                      drafts={inputOverrideDrafts}
                      onDraftChange={updateInputOverrideDraft}
                    />
                  </StackItem>
                )}
              </Stack>
            </StackItem>
          </Stack>
        </div>
      </SynPanel>
    </aside>
  )
}

function getCurrentRetryPlanAnnouncement({
  shouldAnnounce,
  scopeMode,
  selectedCount,
  isLoading,
  preview,
  isError,
  visiblePoints,
}: Readonly<{
  shouldAnnounce: boolean
  scopeMode: RetryScopeMode
  selectedCount: number
  isLoading: boolean
  preview: RetryPreviewState['preview']
  isError: boolean
  visiblePoints: ReturnType<typeof getRetryPlanPoints>
}>): string {
  if (!shouldAnnounce) return ''
  if (scopeMode === 'selected' && selectedCount === 0) {
    return 'Retry plan updated. Choose one or more failure points to see the retry plan.'
  }
  if (isLoading) return 'Updating the retry plan for this selection.'

  const scopeLabel = scopeMode === 'all' ? 'All eligible failure points' : getSelectedScopeLabel(selectedCount)
  return getRetryPlanAnnouncement({ preview, isError, scopeLabel, visiblePoints })
}

function getSelectedScopeLabel(selectedCount: number): string {
  if (selectedCount === 1) return '1 selected failure point'
  return `${selectedCount} selected failure points`
}

function getRetryPlanAnnouncement({
  preview,
  isError,
  scopeLabel,
  visiblePoints,
}: Readonly<{
  preview: RetryPreviewState['preview']
  isError: boolean
  scopeLabel: string
  visiblePoints: ReturnType<typeof getRetryPlanPoints>
}>): string {
  if (isError) return 'Retry plan could not be updated. Change the selection or close and reopen this panel.'
  if (!preview) return 'Retry plan updated. The retry plan is unavailable.'
  if (!preview.eligible) {
    return `Retry plan updated. ${preview.reason ?? 'The selected failure points cannot be retried.'}`
  }

  const stepSummary = getRetryStepSummary(preview.total_step_count)
  const startSummary =
    visiblePoints.length > 0 ? `Retry starts at ${visiblePoints.map((point) => point.name).join(', ')}.` : ''
  const retainedSummary = getRetainedResultSummary(preview.retained_result_count)

  return `Retry plan updated. ${scopeLabel}. ${stepSummary} ${startSummary} ${retainedSummary}`.trim()
}

function getRetryStepSummary(stepCount: number | undefined): string {
  if (stepCount === undefined) return 'The number of steps to retry is unavailable.'
  const stepLabel = stepCount === 1 ? 'step' : 'steps'
  return `${stepCount} ${stepLabel} to retry.`
}

function getRetainedResultSummary(retainedCount: number | undefined): string {
  if (retainedCount === undefined) return 'The number of retained results is unavailable.'
  const resultLabel = retainedCount === 1 ? 'result' : 'results'
  return `${retainedCount} completed ${resultLabel} retained.`
}

function getSelectedPointIds(
  scopeModeOverride: RetryScopeMode | undefined,
  selectedCanvasPointId: string | undefined,
  checkedRetryPointIds: string[]
): string[] {
  if (scopeModeOverride === undefined && selectedCanvasPointId) return [selectedCanvasPointId]
  return checkedRetryPointIds
}

function getRetryPreviewPointIdsKey({
  scopeMode,
  defaultPreview,
  requestedPointIdsKey,
  isLoading,
  activePreview,
}: Readonly<{
  scopeMode: RetryScopeMode
  defaultPreview: RetryFromFailurePreview | undefined
  requestedPointIdsKey: string
  isLoading: boolean
  activePreview: RetryFromFailurePreview | undefined
}>): string {
  if (scopeMode === 'all') {
    if (!defaultPreview?.eligible) return ''
    return eligibleRetryPointIds(defaultPreview).join('\u0000')
  }
  if (isLoading) return requestedPointIdsKey
  if (!activePreview?.eligible) return ''
  return eligibleRetryPointIds(activePreview).join('\u0000')
}

function getActivePreviewLoading(
  scopeMode: RetryScopeMode,
  requestedRetryPointIds: string[],
  defaultPreviewQuery: RetryPreviewState,
  selectedPreviewQuery: RetryPreviewState
): boolean {
  if (scopeMode === 'all') return defaultPreviewQuery.isLoading
  return requestedRetryPointIds.length > 0 && selectedPreviewQuery.isLoading
}
