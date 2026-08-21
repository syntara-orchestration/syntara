import { Alert, Divider, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useEffect, useMemo, useState } from 'react'

import { executionsClient } from '../../client'
import { FilterBar } from '../../components/filters/FilterBar'
import { SynPanel } from '../../components/layout/SynPanel'
import { NxEmptyStateFilter } from '../../components/states/NxEmptyStateFilter'
import { useQueryState } from '../../components/states/useQueryState'
import { useElapsedTime } from '../../hooks/useElapsedTime'
import type { FilterConfig } from '../../types/filters'
import { formatElapsedTime } from '../../utils/dateUtils'
import { detachPromise } from '../../utils/detachPromise'
import { NodeExecutionDetailsPanel } from '../executions/NodeExecutionDetailsPanel'
import type { ActivityState } from '../workflows/execution/types'
import {
  useExecutionStore,
  useExecutionStoreActions,
  useExecutionWithLiveStatus,
  type ExecutionMetadata,
} from '../workflows/stores/useExecutionStore'

import { ACTIVITY_FILTER_DEFINITIONS } from './activityFilterDefinitions'
import { CompactActivityList } from './CompactActivityList'
import { ExecutionActivityTable } from './ExecutionActivityTable'
import type { ActivityOrderItem } from './ExecutionActivityTable'
import styles from './ExecutionDetailsPanel.module.css'
import { HeaderMetadata, LoadingErrorState, NoSelectionState, type ViewMode } from './ExecutionDetailsPanelHeader'
import { useSelectedActivity } from './hooks/useSelectedActivity'
import { useActivityFilters } from './useActivityFilters'
import { useActivityNameMap, type WorkflowDefShape } from './useActivityNameMap'

export type { WorkflowDefShape } from './useActivityNameMap'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

const ACTIVE_STATUSES = new Set<ExecutionStatus>(['running', 'pending', 'paused'])

type ExecutionDetailsPanelProps = {
  executionId: string
  workflowDefinition?: WorkflowDefShape | null
  selectedNodeId?: string | null
  selectedNodeName?: string | null
  onNodeSelect?: (nodeId: string, nodeName: string) => void
  headerLabel?: string
  onClosePanel?: () => void
}

type ThreePanelLayoutProps = {
  execution: {
    started_at?: string | null
    created_at?: string | null
    completed_at?: string | null
    status?: ExecutionStatus | null
  }
  elapsedLabel?: string
  isRunning: boolean
  activityStates: Map<string, ActivityState>
  activityOrder: ActivityOrderItem[]
  hasFilteredOutActivities: boolean
  showFilters: boolean
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  selectedNodeId: string | null
  detailNodeId: string | null
  displayNodeName: string | null
  executionId: string
  selectedNodeState?: ActivityState
  selectedNodeType?: string
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  onRowClick?: (nodeId: string, nodeName: string) => void
  headerLabel?: string
  onClosePanel?: () => void
}

function ThreePanelLayout({
  execution,
  elapsedLabel,
  isRunning,
  activityStates,
  activityOrder,
  hasFilteredOutActivities,
  showFilters,
  filters,
  onFilterChange,
  selectedNodeId,
  detailNodeId,
  displayNodeName,
  executionId,
  selectedNodeState,
  selectedNodeType,
  viewMode,
  onViewModeChange,
  onRowClick,
  headerLabel,
  onClosePanel,
}: Readonly<ThreePanelLayoutProps>) {
  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      style={{
        height: '100%',
        maxHeight: '100%',
        width: '100%',
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      <div className={styles.header}>
        <HeaderMetadata
          execution={execution}
          elapsedLabel={elapsedLabel}
          isRunning={isRunning}
          viewMode={viewMode}
          onViewModeChange={onViewModeChange}
          headerLabel={headerLabel}
          onClosePanel={onClosePanel}
        />
      </div>
      <Flex
        flexWrap={{ default: 'nowrap' }}
        alignItems={{ default: 'alignItemsStretch' }}
        gap={{ default: 'gapNone' }}
        className={styles.contentFlex}
      >
        <FlexItem className={styles.activityList}>
          {showFilters && (
            <section className={styles.filterBarWrapper} aria-label="Activity filter">
              <FilterBar
                fieldDefinitions={ACTIVITY_FILTER_DEFINITIONS}
                filters={filters}
                onFilterChange={onFilterChange}
                isCompact
              />
            </section>
          )}
          <Stack className={styles.activityListScrollWrapper}>
            {activityOrder.length === 0 && hasFilteredOutActivities ? (
              <StackItem isFilled>
                <NxEmptyStateFilter clearAllFilters={() => onFilterChange([])} />
              </StackItem>
            ) : (
              <CompactActivityList
                activityStates={activityStates}
                activityOrder={activityOrder}
                onRowClick={onRowClick}
                selectedNodeId={selectedNodeId}
              />
            )}
          </Stack>
        </FlexItem>

        <Divider orientation={{ default: 'vertical' }} />

        <FlexItem flex={{ default: 'flex_1' }} className={styles.nodeDetailsPane}>
          {detailNodeId && displayNodeName ? (
            <NodeExecutionDetailsPanel
              nodeId={detailNodeId}
              nodeName={displayNodeName}
              executionId={executionId}
              nodeState={selectedNodeState}
              nodeType={selectedNodeType}
            />
          ) : (
            <NoSelectionState />
          )}
        </FlexItem>
      </Flex>
    </SynPanel>
  )
}

function resolveErrorDetails(errorDetails: string | null | undefined, nameMap: Map<string, string>): string | null {
  if (!errorDetails || nameMap.size === 0) return errorDetails ?? null
  let resolved = errorDetails
  for (const [id, name] of nameMap) {
    resolved = resolved.replaceAll(`${id}: `, `${name}: `)
  }
  return resolved
}

type SinglePanelLayoutProps = {
  execution: {
    started_at?: string | null
    created_at?: string | null
    completed_at?: string | null
    status?: ExecutionStatus | null
    error_details?: string | null
  }
  elapsedLabel?: string
  isRunning: boolean
  activityStates: Map<string, ActivityState>
  activityOrder: ActivityOrderItem[]
  nameMap: Map<string, string>
  hasFilteredOutActivities: boolean
  showFilters: boolean
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  now: number
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  onRowClick?: (nodeId: string, nodeName: string) => void
  selectedNodeId?: string | null
  headerLabel?: string
  onClosePanel?: () => void
}

function SinglePanelLayout({
  execution,
  elapsedLabel,
  isRunning,
  activityStates,
  activityOrder,
  nameMap,
  hasFilteredOutActivities,
  showFilters,
  filters,
  onFilterChange,
  now,
  viewMode,
  onViewModeChange,
  onRowClick,
  selectedNodeId,
  headerLabel,
  onClosePanel,
}: Readonly<SinglePanelLayoutProps>) {
  const resolvedError = useMemo(
    () => resolveErrorDetails(execution.error_details, nameMap),
    [execution.error_details, nameMap]
  )
  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      style={{
        height: '100%',
        maxHeight: '100%',
        width: '100%',
        flexShrink: 0,
      }}
    >
      <Stack style={{ height: '100%', overflow: 'hidden', padding: 'var(--pf-t--global--spacer--md)' }}>
        <StackItem style={{ flexShrink: 0, paddingBottom: 'var(--pf-t--global--spacer--md)' }}>
          <HeaderMetadata
            execution={execution}
            elapsedLabel={elapsedLabel}
            isRunning={isRunning}
            viewMode={viewMode}
            onViewModeChange={onViewModeChange}
            headerLabel={headerLabel}
            onClosePanel={onClosePanel}
          />
        </StackItem>

        {showFilters && (
          <StackItem className={styles.filterBarWrapper}>
            <section aria-label="Activity filter">
              <FilterBar
                fieldDefinitions={ACTIVITY_FILTER_DEFINITIONS}
                filters={filters}
                onFilterChange={onFilterChange}
                isCompact
              />
            </section>
          </StackItem>
        )}

        {execution.status === 'failed' && resolvedError && (
          <StackItem style={{ flexShrink: 0, paddingBottom: 'var(--pf-t--global--spacer--sm)' }}>
            <Alert variant="danger" isInline isPlain title="Execution failed">
              {resolvedError}
            </Alert>
          </StackItem>
        )}

        {activityOrder.length === 0 && hasFilteredOutActivities ? (
          <StackItem isFilled style={{ minHeight: 0 }}>
            <NxEmptyStateFilter clearAllFilters={() => onFilterChange([])} />
          </StackItem>
        ) : (
          <ExecutionActivityTable
            activityStates={activityStates}
            activityOrder={activityOrder}
            now={now}
            executionError={resolvedError}
            onRowClick={onRowClick}
            selectedNodeId={selectedNodeId}
          />
        )}
      </Stack>
    </SynPanel>
  )
}

export function ExecutionDetailsPanel({
  executionId,
  workflowDefinition,
  selectedNodeId,
  selectedNodeName: selectedNodeNameProp,
  onNodeSelect,
  headerLabel,
  onClosePanel,
}: Readonly<ExecutionDetailsPanelProps>) {
  const { setActivityExecutions } = useExecutionStoreActions()
  const activityStates = useExecutionStore((s) => s.activityStates)
  const [viewMode, setViewMode] = useState<ViewMode>('overview')

  const executionQuery = executionsClient.useQuery('get', '/executions/{execution_id}', {
    params: {
      path: { execution_id: executionId },
      query: { include: 'activities' },
    },
  })

  const execution = useExecutionWithLiveStatus(executionQuery.data)
  const isRunning = execution?.status != null && ACTIVE_STATUSES.has(execution.status)
  const startedAtValue = execution?.created_at ?? null

  const { elapsedMs, now } = useElapsedTime(startedAtValue, execution?.completed_at, isRunning)
  const elapsedLabel = elapsedMs !== undefined ? formatElapsedTime(elapsedMs) : undefined

  const activities = execution?.activities
  const executionMetadata = (execution as { execution_metadata?: ExecutionMetadata } | undefined)?.execution_metadata

  const { injectPreResolvedStates, setExecutionMetadata } = useExecutionStore.getState()

  useEffect(() => {
    if (activities) {
      setActivityExecutions(activities)
    }

    // Pre-resolved nodes may not have ActivityExecution records yet (backend race).
    // Inject SKIPPED states for any that are missing from the activity list.
    const preResolved = executionMetadata?.pre_resolved_nodes
    if (preResolved) {
      const existingIds = new Set((activities ?? []).map((a) => a.activity_id))
      const missing = Object.keys(preResolved).filter((id) => !existingIds.has(id))
      injectPreResolvedStates(missing)
    }

    setExecutionMetadata(executionMetadata ?? null)
  }, [activities, executionMetadata, setActivityExecutions, injectPreResolvedStates, setExecutionMetadata])

  const { nameMap, activityOrder } = useActivityNameMap(workflowDefinition, activityStates)

  const { filters, filteredActivityOrder, handleFilterChange, hasActiveFilters } = useActivityFilters(
    activityOrder,
    activityStates
  )

  const hasFilteredOutActivities = hasActiveFilters && activityOrder.length > 0
  const showFilters = activityOrder.length > 0 || hasActiveFilters

  const { resolvedNodeId, effectiveKey, displayNodeName, selectedNodeState, selectedNodeType, handleRowClick } =
    useSelectedActivity({
      selectedNodeId,
      selectedNodeNameProp,
      activityStates,
      activityOrder,
      nameMap,
      onNodeSelect,
    })

  const queryState = useQueryState(executionQuery, {
    title: 'Error loading execution',
    onRetry: () => detachPromise(executionQuery.refetch()),
  })

  if (queryState || !execution) {
    return <LoadingErrorState queryState={queryState} />
  }

  if (viewMode === 'details') {
    return (
      <ThreePanelLayout
        execution={execution}
        elapsedLabel={elapsedLabel}
        isRunning={isRunning}
        activityStates={activityStates}
        activityOrder={filteredActivityOrder}
        hasFilteredOutActivities={hasFilteredOutActivities}
        showFilters={showFilters}
        filters={filters}
        onFilterChange={handleFilterChange}
        selectedNodeId={resolvedNodeId}
        detailNodeId={effectiveKey}
        displayNodeName={displayNodeName}
        executionId={executionId}
        selectedNodeState={selectedNodeState}
        selectedNodeType={selectedNodeType}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onRowClick={handleRowClick}
        headerLabel={headerLabel}
        onClosePanel={onClosePanel}
      />
    )
  }

  return (
    <SinglePanelLayout
      execution={execution}
      elapsedLabel={elapsedLabel}
      isRunning={isRunning}
      activityStates={activityStates}
      activityOrder={filteredActivityOrder}
      nameMap={nameMap}
      hasFilteredOutActivities={hasFilteredOutActivities}
      showFilters={showFilters}
      filters={filters}
      onFilterChange={handleFilterChange}
      now={now}
      viewMode={viewMode}
      onViewModeChange={setViewMode}
      onRowClick={handleRowClick}
      selectedNodeId={resolvedNodeId}
      headerLabel={headerLabel}
      onClosePanel={onClosePanel}
    />
  )
}
