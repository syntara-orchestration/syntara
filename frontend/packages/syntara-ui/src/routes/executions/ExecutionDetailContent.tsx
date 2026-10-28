import { Flex, FlexItem } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'
import type React from 'react'

import { SynPanelStack, SynPanelStackItem } from '../../components/layout/SynPanelStack'
import { ResizableDivider } from '../../components/ResizableDivider'
import type { PaginationFooterProps } from '../../components/table/PaginationFooter'
import { useAlerts } from '../../providers/alerts'
import type { FilterConfig } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { ExecutionDetailsPanel, type WorkflowDefShape } from '../builder/ExecutionDetailsPanel'
import { ExecutionViewContent } from '../builder/ExecutionViewContent'
import { WorkflowHistoryCard } from '../builder/WorkflowHistoryCard'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import { ConnectionBanner } from './ConnectionBanner'
import styles from './ExecutionDetail.module.css'
import { RetryFromFailureSidePanel } from './RetryFromFailureSidePanel'
import { useRetryInputOverrides } from './useRetryInputOverrides'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

type ExecutionWorkflow = {
  id: string
  name: string
  description?: string
  version: { workflow_definition: WorkflowDefShape | null }
}

type ExecutionDetailContentProps = Readonly<{
  historyCardOpen: boolean
  approvalPanel?: React.ReactNode
  retryPanelOpen: boolean
  activityNameMap: ReadonlyMap<string, string>
  activityTypeMap: ReadonlyMap<string, string>
  onRetryPanelClose: () => void
  workflow?: ExecutionWorkflow
  execution: Execution | undefined
  activities: (ActivityData | ActivityExecution)[]
  executionId: string
  executionsQuery: {
    data?: { resources?: Execution[] }
    isLoading: boolean
    error: unknown
    refetch: () => Promise<unknown>
  }
  navigate: ReturnType<typeof import('@tanstack/react-router').useNavigate>
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  paginationFooterProps: PaginationFooterProps
  onNodeClick?: (event: React.MouseEvent, node: { id: string; type?: string; data: Record<string, unknown> }) => void
  selectedStepId: string | null
  selectedStepName: string | null
  onStepSelect: (stepId: string, stepName: string) => void
  currentApprovalNodeId?: string | null
}>

type ExecutionDetailContentLayoutProps = Readonly<{
  historyCardOpen: boolean
  approvalPanel?: React.ReactNode
  retryPanel?: React.ReactNode
  workflow?: ExecutionWorkflow
  execution: Execution | undefined
  activities: (ActivityData | ActivityExecution)[]
  executionId: string
  executionsQuery: ExecutionDetailContentProps['executionsQuery']
  navigate: ExecutionDetailContentProps['navigate']
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  paginationFooterProps: PaginationFooterProps
  onNodeClick?: ExecutionDetailContentProps['onNodeClick']
  selectedStepId: string | null
  onStepSelect: (stepId: string, stepName: string) => void
  currentApprovalNodeId?: string | null
  retryPreviewPointIds: string[]
  retryDetailNodeId: string | null
  retryDetailNodeName: string | null
  retryMode: boolean
  retryInputOverrides?: ReturnType<typeof useRetryInputOverrides>['state']
  panelHeight: number
  panelHeightPercent: number
  onResize: (deltaY: number) => void
}>

function ExecutionDetailContentLayout({
  historyCardOpen,
  approvalPanel,
  retryPanel,
  workflow,
  execution,
  activities,
  executionId,
  executionsQuery,
  navigate,
  filters,
  onFilterChange,
  paginationFooterProps,
  onNodeClick,
  selectedStepId,
  onStepSelect,
  currentApprovalNodeId,
  retryPreviewPointIds,
  retryDetailNodeId,
  retryDetailNodeName,
  retryMode,
  retryInputOverrides,
  panelHeight,
  panelHeightPercent,
  onResize,
}: ExecutionDetailContentLayoutProps) {
  const isStale = useExecutionStore((state) => state.isStale)
  const isComplete = useExecutionStore((state) => state.isComplete)

  return (
    <Flex
      alignItems={{ default: 'alignItemsStretch' }}
      flexWrap={{ default: 'nowrap' }}
      gap={{ default: 'gapLg' }}
      style={{
        position: 'relative',
        minWidth: 0,
        height: '100%',
        overflow: 'visible',
        display: 'flex',
        flexDirection: 'row',
      }}
    >
      <FlexItem
        style={{
          position: 'relative',
          minWidth: 0,
          flexGrow: 1,
          height: '100%',
        }}
      >
        {isStale && !isComplete && (
          <Flex
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              zIndex: 10,
              padding: 'var(--pf-t--global--spacer--md)',
              pointerEvents: 'auto',
            }}
            onMouseDown={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
          >
            <FlexItem fullWidth={{ default: 'fullWidth' }}>
              <ConnectionBanner isVisible />
            </FlexItem>
          </Flex>
        )}
        <SynPanelStack>
          <SynPanelStackItem isFilled>
            <ExecutionViewContent
              workflow={workflow}
              executionStatus={execution?.status ?? null}
              executionActivities={activities}
              executionId={executionId}
              onNodeClick={onNodeClick}
              selectedActivityId={currentApprovalNodeId ?? selectedStepId}
              retryPreviewPointIds={retryPreviewPointIds}
            />
          </SynPanelStackItem>

          <ResizableDivider onResize={onResize} currentValue={panelHeightPercent} />

          <SynPanelStackItem style={{ height: `${String(panelHeight)}px` }}>
            <ExecutionDetailsPanel
              executionId={executionId}
              workflowDefinition={workflow?.version.workflow_definition}
              selectedNodeId={retryDetailNodeId}
              selectedNodeName={retryDetailNodeName}
              onNodeSelect={onStepSelect}
              retryMode={retryMode}
              retryInputOverrides={retryInputOverrides}
            />
          </SynPanelStackItem>
        </SynPanelStack>
      </FlexItem>

      {approvalPanel && <FlexItem className={styles.approvalPanelSlot}>{approvalPanel}</FlexItem>}
      {retryPanel && <FlexItem className={styles.approvalPanelSlot}>{retryPanel}</FlexItem>}

      {historyCardOpen && (
        <FlexItem className={styles.approvalPanelSlot}>
          <WorkflowHistoryCard
            executions={executionsQuery.data?.resources ?? []}
            selectedExecutionId={executionId}
            onClose={() => {
              detachPromise(
                navigate({
                  to: '/executions/$executionId',
                  params: { executionId },
                  search: (prev: Record<string, unknown>) => ({ ...prev, history: 'closed' }),
                })
              )
            }}
            onExecutionSelect={(selectedId) => {
              detachPromise(
                navigate({
                  to: '/executions/$executionId',
                  params: { executionId: selectedId },
                  search: (prev: Record<string, unknown>) => ({ ...prev }),
                })
              )
            }}
            filters={filters}
            onFilterChange={onFilterChange}
            paginationFooterProps={paginationFooterProps}
          />
        </FlexItem>
      )}
    </Flex>
  )
}

export function ExecutionDetailContent(props: ExecutionDetailContentProps) {
  const {
    historyCardOpen,
    approvalPanel,
    retryPanelOpen,
    activityNameMap,
    activityTypeMap,
    onRetryPanelClose,
    workflow,
    execution,
    activities,
    executionId,
    executionsQuery,
    navigate,
    filters,
    onFilterChange,
    paginationFooterProps,
    onNodeClick,
    selectedStepId,
    selectedStepName,
    onStepSelect,
    currentApprovalNodeId,
  } = props
  const { showError } = useAlerts()
  const prevStatusRef = useRef(execution?.status)
  const [panelHeight, setPanelHeight] = useState(300)
  const [retryPreviewPointIds, setRetryPreviewPointIds] = useState<string[]>([])
  const {
    savedOverrides: retryInputParameterOverrides,
    hasUnsavedInputOverrides,
    state: retryInputOverridesState,
    setPointIds: setRetryInputOverridePointIds,
    reset: resetRetryInputOverrides,
  } = useRetryInputOverrides({
    enabled: retryPanelOpen,
    executionProjectId: execution?.project_id,
    workflowDefinition: workflow?.version.workflow_definition,
    activityNameMap,
    activities,
  })

  const closeRetryReview = useCallback(() => {
    setRetryPreviewPointIds([])
    resetRetryInputOverrides()
    onRetryPanelClose()
  }, [onRetryPanelClose, resetRetryInputOverrides])
  const firstRetryPointId = retryPreviewPointIds[0]
  const selectedRetryPointId = selectedStepId
    ? retryPreviewPointIds.find(
        (pointId) => parseCompositeKey(pointId).baseId === parseCompositeKey(selectedStepId).baseId
      )
    : undefined
  const retryDetailPointId = selectedRetryPointId ?? firstRetryPointId
  const retryDetailNodeId = retryPanelOpen ? (retryDetailPointId ?? selectedStepId) : selectedStepId
  const retryDetailNodeBaseId = retryDetailPointId ? parseCompositeKey(retryDetailPointId).baseId : null
  const retryDetailNodeName =
    retryPanelOpen && retryDetailNodeBaseId
      ? (activityNameMap.get(retryDetailNodeBaseId) ?? selectedStepName ?? retryDetailNodeBaseId)
      : selectedStepName
  const retryPanel = retryPanelOpen ? (
    <RetryFromFailureSidePanel
      executionId={executionId}
      activityNameMap={activityNameMap}
      activityTypeMap={activityTypeMap}
      selectedNodeId={selectedStepId}
      inputParameterOverrides={retryInputParameterOverrides}
      hasUnsavedInputOverrides={hasUnsavedInputOverrides}
      onRetryPreviewPointIdsChange={setRetryPreviewPointIds}
      onRetryInputOverridePointIdsChange={setRetryInputOverridePointIds}
      onClose={closeRetryReview}
    />
  ) : undefined

  const showFailureToast = useCallback(() => {
    showError({
      title: `${workflow?.name ?? 'Workflow'} run failed`,
      description: 'View the run logs and copy to the editor to debug within the editor',
    })
  }, [workflow?.name, showError])

  useEffect(() => {
    const prevStatus = prevStatusRef.current
    prevStatusRef.current = execution?.status

    if (execution?.status === 'failed' && prevStatus && prevStatus !== 'failed') {
      showFailureToast()
    }
  }, [execution?.status, showFailureToast])

  const handleResize = useCallback((deltaY: number) => {
    setPanelHeight((prev) => Math.min(600, Math.max(100, prev - deltaY)))
  }, [])
  const panelHeightPercent = Math.round(((panelHeight - 100) / 500) * 100)

  return (
    <ExecutionDetailContentLayout
      historyCardOpen={historyCardOpen}
      approvalPanel={approvalPanel}
      retryPanel={retryPanel}
      workflow={workflow}
      execution={execution}
      activities={activities}
      executionId={executionId}
      executionsQuery={executionsQuery}
      navigate={navigate}
      filters={filters}
      onFilterChange={onFilterChange}
      paginationFooterProps={paginationFooterProps}
      onNodeClick={onNodeClick}
      selectedStepId={selectedStepId}
      onStepSelect={onStepSelect}
      currentApprovalNodeId={currentApprovalNodeId}
      retryPreviewPointIds={retryPreviewPointIds}
      retryDetailNodeId={retryDetailNodeId}
      retryDetailNodeName={retryDetailNodeName}
      retryMode={retryPanelOpen}
      retryInputOverrides={retryPanelOpen ? retryInputOverridesState : undefined}
      panelHeight={panelHeight}
      panelHeightPercent={panelHeightPercent}
      onResize={handleResize}
    />
  )
}
