import { HelperText, HelperTextItem, Stack, StackItem, Title, TitleSizes } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import { useEffect, useEffectEvent, useId, useLayoutEffect, useRef, useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { detachPromise } from '../../utils/detachPromise'
import { getNotRetriedFailureCount, type RetryPreviewGraphEdge } from '../builder/retryPreviewCanvasState'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import {
  canConfirmRetryFromFailure,
  eligibleRetryPointIds,
  getRetryInputOverridePointIds,
  getRetryPlanPoints,
  getSanitizedOutputWarning,
  getUnavailableRetryPlanPoints,
  type RetryFromFailurePreview,
} from './retryFromFailure'
import styles from './RetryFromFailureSidePanel.module.css'
import {
  HowRetryWorks,
  RetryFooter,
  RetryPlan,
  SanitizedOutputAlert,
  type RetryScopeMode,
} from './RetryFromFailureSidePanelParts'

const EMPTY_RETRY_GRAPH_EDGES: readonly RetryPreviewGraphEdge[] = []
const EMPTY_FAILED_ACTIVITY_IDS: readonly string[] = []

type RetryFromFailureSidePanelProps = Readonly<{
  executionId: string
  activityNameMap: ReadonlyMap<string, string>
  activityTypeMap: ReadonlyMap<string, string>
  workflowEdges?: readonly RetryPreviewGraphEdge[]
  failedActivityIds?: readonly string[]
  inputParameterOverrides?: Readonly<Record<string, Record<string, unknown>>>
  hasUnsavedInputOverrides?: boolean
  onRetryPreviewPointIdsChange?: (pointIds: string[]) => void
  onRetryInputOverridePointIdsChange?: (pointIds: string[]) => void
  onClose: () => void
}>

type RetryPreviewState = ReturnType<typeof useRetryFromFailurePreview>

/** Full in-context retry review shown beside the source execution. */
export function RetryFromFailureSidePanel({
  executionId,
  activityNameMap,
  activityTypeMap,
  workflowEdges = EMPTY_RETRY_GRAPH_EDGES,
  failedActivityIds = EMPTY_FAILED_ACTIVITY_IDS,
  inputParameterOverrides = {},
  hasUnsavedInputOverrides = false,
  onRetryPreviewPointIdsChange,
  onRetryInputOverridePointIdsChange,
  onClose,
}: RetryFromFailureSidePanelProps) {
  const navigate = useNavigate()
  const scopeId = useId()
  const panelRef = useRef<HTMLElement | null>(null)
  const {
    scopeMode,
    checkedRetryPointIds,
    shouldAnnounceRetryPlan,
    setAllRetryPoints,
    chooseRetryPoints,
    updateRetryPoint,
  } = useRetryScopeSelection()

  const defaultPreviewQuery = useRetryFromFailurePreview({ executionId, enabled: true })
  const defaultPoints = getRetryPlanPoints(defaultPreviewQuery.preview, activityNameMap, activityTypeMap)
  const selectedPointIdSet = new Set(checkedRetryPointIds)
  const requestedRetryPointIds = defaultPoints
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
  const unavailablePoints = getUnavailableRetryPlanPoints(activePreview, activityNameMap, activityTypeMap)
  const retryPlanPointIds = activePreview?.eligible ? eligibleRetryPointIds(activePreview) : requestedRetryPointIds
  const notRetriedFailureCount = getPanelNotRetriedFailureCount({
    activePreview,
    failedActivityIds,
    requestedRetryPointIds,
    retryPlanPointIds,
    scopeMode,
    workflowEdges,
  })
  const retryPlanAnnouncement = getCurrentRetryPlanAnnouncement({
    shouldAnnounce: shouldAnnounceRetryPlan,
    scopeMode,
    selectedCount: requestedRetryPointIds.length,
    isLoading: activeIsLoading,
    preview: activePreview,
    isError: activeIsError,
    visiblePoints,
  })

  useLayoutEffect(() => panelRef.current?.focus(), [])

  const requestedRetryPointIdsKey = requestedRetryPointIds.join('\u0000')
  const retryPreviewPointIdsKey = getRetryPreviewPointIdsKey({
    scopeMode,
    defaultPreview: defaultPreviewQuery.preview,
    requestedPointIdsKey: requestedRetryPointIdsKey,
    isLoading: activeIsLoading,
    activePreview,
  })
  const retryInputOverridePointIds = getRetryInputOverridePointIds(activePreview, failedActivityIds, workflowEdges)
  const retryInputOverridePointIdsKey = retryInputOverridePointIds.join('\u0000')
  const notifyRetryPreviewPointIdsChange = useEffectEvent((pointIds: string[]) => {
    onRetryPreviewPointIdsChange?.(pointIds)
  })
  const notifyRetryInputOverridePointIdsChange = useEffectEvent((pointIds: string[]) => {
    onRetryInputOverridePointIdsChange?.(pointIds)
  })

  useEffect(() => {
    notifyRetryPreviewPointIdsChange(retryPreviewPointIdsKey ? retryPreviewPointIdsKey.split('\u0000') : [])
  }, [retryPreviewPointIdsKey])
  useEffect(() => {
    notifyRetryInputOverridePointIdsChange(
      retryInputOverridePointIdsKey ? retryInputOverridePointIdsKey.split('\u0000') : []
    )
  }, [retryInputOverridePointIdsKey])

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
    hasUnsavedInputOverrides ||
    retry.isPending
  const submitInputParameterOverrides = pickRetryInputParameterOverrides(
    retryInputOverridePointIds,
    inputParameterOverrides
  )

  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      className={styles.panel}
      aria-label="Retry run from failure review"
      data-testid="retry-from-failure-panel"
    >
      <SynPanel
        hasNoPadding
        isFullHeight
        isScrollable
        footer={
          <RetryFooter
            onRetry={() =>
              retry.handleRetry(scopeMode === 'all' ? undefined : requestedRetryPointIds, submitInputParameterOverrides)
            }
            onCancel={onClose}
            isRetryDisabled={isRetryDisabled}
            isRetryPending={retry.isPending}
            stepCount={activePreview?.total_step_count}
          />
        }
      >
        <div className={styles.panelInner}>
          <Stack className={styles.panelStack}>
            <StackItem className={styles.headerPadding}>
              <SidePanelHeader title="Retry run from failure" onClose={onClose} closeAriaLabel="Close retry review" />
            </StackItem>
            <StackItem isFilled className={styles.bodyPadding}>
              <Stack hasGutter>
                <SanitizedOutputAlert warning={getSanitizedOutputWarning(activePreview, activityNameMap)} />
                <StackItem>
                  <HowRetryWorks />
                </StackItem>
                <StackItem className={styles.retryPlanSection}>
                  <Title headingLevel="h3" size={TitleSizes.md}>
                    Retry plan
                  </Title>
                  <div className={styles.retryPlanCard} data-testid="retry-plan-card">
                    <RetryPlan
                      defaultPreview={defaultPreviewQuery.preview}
                      defaultIsLoading={defaultPreviewQuery.isLoading}
                      defaultIsError={defaultPreviewQuery.isError}
                      activePreview={activePreview}
                      activeIsLoading={activeIsLoading}
                      activeIsError={activeIsError}
                      defaultPoints={defaultPoints}
                      selectablePoints={defaultPoints}
                      visiblePoints={visiblePoints}
                      unavailablePoints={unavailablePoints}
                      notRetriedFailureCount={notRetriedFailureCount}
                      requestedRetryPointIds={requestedRetryPointIds}
                      selectedPointCount={requestedRetryPointIds.length}
                      scopeMode={scopeMode}
                      scopeId={scopeId}
                      isRetryPending={retry.isPending || hasUnsavedInputOverrides}
                      onSelectAll={setAllRetryPoints}
                      onChoosePoints={chooseRetryPoints}
                      onUpdatePoint={updateRetryPoint}
                    />
                  </div>
                  <div className="pf-v6-u-screen-reader" role="status" aria-live="polite" aria-atomic="true">
                    {retryPlanAnnouncement}
                  </div>
                </StackItem>
                {hasUnsavedInputOverrides && (
                  <StackItem>
                    <HelperText>
                      <HelperTextItem variant="warning">
                        Save or cancel input changes in Run details before retrying.
                      </HelperTextItem>
                    </HelperText>
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

function useRetryScopeSelection() {
  const [scopeMode, setScopeMode] = useState<RetryScopeMode>('all')
  const [checkedRetryPointIds, setCheckedRetryPointIds] = useState<string[]>([])
  const [shouldAnnounceRetryPlan, setShouldAnnounceRetryPlan] = useState(false)

  const setAllRetryPoints = () => {
    setShouldAnnounceRetryPlan(true)
    setScopeMode('all')
    setCheckedRetryPointIds([])
  }

  const chooseRetryPoints = () => {
    setShouldAnnounceRetryPlan(true)
    setScopeMode('selected')
    setCheckedRetryPointIds([])
  }

  const updateRetryPoint = (pointId: string, isChecked: boolean) => {
    setShouldAnnounceRetryPlan(true)
    setScopeMode('selected')
    setCheckedRetryPointIds((currentIds) => {
      if (isChecked) return [...new Set([...currentIds, pointId])]
      return currentIds.filter((id) => id !== pointId)
    })
  }

  return {
    scopeMode,
    checkedRetryPointIds,
    shouldAnnounceRetryPlan,
    setAllRetryPoints,
    chooseRetryPoints,
    updateRetryPoint,
  }
}

function pickRetryInputParameterOverrides(
  pointIds: readonly string[],
  overrides: Readonly<Record<string, Record<string, unknown>>>
): Record<string, Record<string, unknown>> {
  return Object.fromEntries(
    pointIds.flatMap((pointId) => {
      const value = overrides[pointId]
      return value && Object.keys(value).length > 0 ? [[pointId, value] as const] : []
    })
  )
}

function getPanelNotRetriedFailureCount({
  activePreview,
  failedActivityIds,
  requestedRetryPointIds,
  retryPlanPointIds,
  scopeMode,
  workflowEdges,
}: Readonly<{
  activePreview: RetryPreviewState['preview']
  failedActivityIds: readonly string[]
  requestedRetryPointIds: readonly string[]
  retryPlanPointIds: readonly string[]
  scopeMode: RetryScopeMode
  workflowEdges: readonly RetryPreviewGraphEdge[]
}>): number {
  if (scopeMode !== 'selected' || requestedRetryPointIds.length === 0 || !activePreview?.eligible) return 0
  return getNotRetriedFailureCount(failedActivityIds, retryPlanPointIds, workflowEdges)
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
    return 'Retry plan updated. Choose one or more steps to see the retry plan.'
  }
  if (isLoading) return 'Updating the retry plan for this selection.'

  const scopeLabel = scopeMode === 'all' ? 'All affected steps' : getSelectedScopeLabel(selectedCount)
  return getRetryPlanAnnouncement({ preview, isError, scopeLabel, visiblePoints })
}

function getSelectedScopeLabel(selectedCount: number): string {
  if (selectedCount === 1) return '1 selected step'
  return `${selectedCount} selected steps`
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
    return `Retry plan updated. ${preview.reason ?? 'The selected steps cannot be retried.'}`
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
