import { Flex, FlexItem, TitleSizes } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import type React from 'react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useRef, useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanelStack, SynPanelStackItem } from '../../components/layout/SynPanelStack'
import { SynReactFlowViewportGuard } from '../../components/layout/SynReactFlowViewportGuard'
import { ResizableDivider } from '../../components/ResizableDivider'
import { SynPageTitle } from '../../components/SynPageTitle'
import type { PaginationFooterProps } from '../../components/table/PaginationFooter'
import { useAlerts } from '../../providers/alerts'
import type { FilterConfig } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'
import { ExecutionDetailsPanel, type WorkflowDefShape } from '../builder/ExecutionDetailsPanel'
import { ExecutionViewContent } from '../builder/ExecutionViewContent'
import { WorkflowHistoryCard } from '../builder/WorkflowHistoryCard'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import { ExecutionDetailErrorStates } from './components/ExecutionDetailErrorStates'
import { ConnectionBanner } from './ConnectionBanner'
import { CopyToEditorDialog } from './CopyToEditorDialog'
import styles from './ExecutionDetail.module.css'
import { resolveWaitingNodeHighlightId } from './executionDetailHighlight'
import { ExecutionDetailHeaderToolbar, ExecutionDetailTitleRowAddons } from './ExecutionDetailPageHeaderParts'
import { executionDetailHasTitleRowExtras, executionDetailPageHeading } from './executionDetailPageHeaderTitle'
import { ExecutionDetailSidePanel } from './ExecutionDetailSidePanel'
import { useExecutionDetailPageModel, useResetOnExecutionChange } from './hooks/useExecutionDetailPageModel'

/** Returns true when the page should render a fallback (missing ID, loading, or error) instead of the main content. */
function shouldShowFallbackState(
  executionId: string | undefined,
  query: { isLoading: boolean; error: unknown }
): boolean {
  return !executionId || query.isLoading || !!query.error
}

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

type ExecutionWorkflow = {
  id: string
  name: string
  description?: string
  version: { workflow_definition: WorkflowDefShape | null }
}

// Inner component that has access to React Flow context
function ExecutionDetailContent({
  historyCardOpen,
  approvalPanel,
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
  selectedNodeId,
  selectedNodeName,
  onNodeSelect,
  currentApprovalNodeId,
}: Readonly<{
  historyCardOpen: boolean
  approvalPanel?: React.ReactNode
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
  navigate: ReturnType<typeof useNavigate>
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  paginationFooterProps: PaginationFooterProps
  onNodeClick?: (event: React.MouseEvent, node: { id: string; type?: string; data: Record<string, unknown> }) => void
  selectedNodeId: string | null
  selectedNodeName: string | null
  onNodeSelect: (nodeId: string, nodeName: string) => void
  currentApprovalNodeId?: string | null
}>) {
  const isStale = useExecutionStore((state) => state.isStale)
  const isComplete = useExecutionStore((state) => state.isComplete)
  const { showError } = useAlerts()
  const prevStatusRef = useRef(execution?.status)
  const [panelHeight, setPanelHeight] = useState(300)

  const showFailureToast = useCallback(() => {
    showError({
      title: `${workflow?.name ?? 'Workflow'} run failed`,
      description: 'View the run logs and copy to the editor to debug within the editor',
    })
  }, [workflow?.name, showError])

  /* eslint-disable reactYouMightNotNeedAnEffect/no-event-handler -- toast when run transitions to failed */
  useEffect(() => {
    const prevStatus = prevStatusRef.current
    prevStatusRef.current = execution?.status

    if (execution?.status === 'failed' && prevStatus && prevStatus !== 'failed') {
      showFailureToast()
    }
  }, [execution?.status, showFailureToast])
  /* eslint-enable reactYouMightNotNeedAnEffect/no-event-handler */

  const MIN_PANEL_HEIGHT = 100
  const MAX_PANEL_HEIGHT = 600

  const handleResize = useCallback((deltaY: number) => {
    setPanelHeight((prev) => Math.min(MAX_PANEL_HEIGHT, Math.max(MIN_PANEL_HEIGHT, prev - deltaY)))
  }, [])

  const panelHeightPercent = Math.round(
    ((panelHeight - MIN_PANEL_HEIGHT) / (MAX_PANEL_HEIGHT - MIN_PANEL_HEIGHT)) * 100
  )

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
              selectedActivityId={currentApprovalNodeId ?? selectedNodeId}
            />
          </SynPanelStackItem>

          <ResizableDivider onResize={handleResize} currentValue={panelHeightPercent} />

          <SynPanelStackItem style={{ height: `${String(panelHeight)}px` }}>
            <ExecutionDetailsPanel
              executionId={executionId}
              workflowDefinition={workflow?.version.workflow_definition}
              selectedNodeId={selectedNodeId}
              selectedNodeName={selectedNodeName}
              onNodeSelect={onNodeSelect}
            />
          </SynPanelStackItem>
        </SynPanelStack>
      </FlexItem>

      {approvalPanel && <FlexItem className={styles.approvalPanelSlot}>{approvalPanel}</FlexItem>}

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

export default function ExecutionDetail() {
  const executionsDocLink = useDocLink('executions')
  const page = useExecutionDetailPageModel()

  useResetOnExecutionChange(page.executionId)

  if (shouldShowFallbackState(page.executionId, page.executionQuery)) {
    return (
      <ExecutionDetailErrorStates
        executionId={page.executionId}
        isLoading={page.executionQuery.isLoading}
        error={page.executionQuery.error}
        onRetry={page.executionQuery.refetch}
      />
    )
  }

  const { execution, executionId, navigate } = page

  return (
    <SynPage>
      <SynPageTitle segments={[executionDetailPageHeading(execution, executionId), 'Workflow Runs']} />
      <SynReactFlowViewportGuard onReturn={() => detachPromise(navigate({ to: AppRoute.Executions.Root }))}>
        <SynPageHeader
          title={executionDetailPageHeading(execution, executionId)}
          docLink={executionsDocLink}
          titleProps={{ size: TitleSizes['2xl'] }}
          titleAddons={
            executionDetailHasTitleRowExtras(execution) ? (
              <ExecutionDetailTitleRowAddons execution={execution} />
            ) : undefined
          }
          toolbar={
            <ExecutionDetailHeaderToolbar
              showApprovalActionStrip={Boolean(page.currentApproval ?? page.isApprovalLoading)}
              isApprovalLoading={page.isApprovalLoading}
              isApprovalPanelOpen={page.approval.panelOpen}
              onReviewClick={page.approval.open}
              showFormPromptActionStrip={Boolean(
                page.isFormPromptLoading || page.currentFormPrompt?.status === 'pending'
              )}
              isFormPromptLoading={page.isFormPromptLoading}
              isFormPromptPanelOpen={page.formPromptPanel.panelOpen}
              onRespondClick={page.formPromptPanel.open}
              historyCardOpen={page.historyCardOpen}
              onToggleHistory={page.toggleHistoryCard}
              onBackToEditor={() => {
                if (execution?.workflow_id) {
                  detachPromise(
                    navigate({ to: '/workflow-builder/$workflowId', params: { workflowId: execution.workflow_id } })
                  )
                }
              }}
              onCopyToEditor={() => page.copyToEditorDialog.open(undefined)}
              isCancellable={page.isCancellable}
              executionId={executionId}
              execution={execution}
            />
          }
        />
        <SynPageBody>
          <ExecutionDetailContent
            key={executionId}
            historyCardOpen={page.historyCardOpen && !page.approval.panelOpen && !page.formPromptPanel.panelOpen}
            approvalPanel={
              page.hasOpenExecutionSidePanel ? (
                <ExecutionDetailSidePanel
                  formPromptPanelOpen={page.formPromptPanel.panelOpen}
                  currentFormPrompt={page.currentFormPrompt}
                  formPromptNavigation={page.formPromptNavigation}
                  formPromptIndex={page.formPromptIndex}
                  formPromptCount={page.formPrompts.length}
                  executionId={executionId}
                  activityNameMap={page.activityNameMap}
                  onFormPromptClose={page.formPromptPanel.close}
                  onFormPromptSubmitted={page.formPromptPanel.dismiss}
                  workflowDefinition={page.workflowDefinitionForSidePanel}
                  approvalPanelOpen={page.approval.panelOpen}
                  currentApproval={page.currentApproval}
                  approvalMessage={page.approval.approvalMessage}
                  approvalNavigation={page.approvalNavigation}
                  currentApprovalIndex={page.currentIndex}
                  approvalCount={page.approvals.length}
                  onApprovalClose={page.approval.close}
                  onApprovalDecisionSubmitted={page.approval.dismiss}
                  onNavigate={(path) => detachPromise(navigate({ to: path }))}
                />
              ) : undefined
            }
            workflow={page.workflow}
            execution={execution}
            activities={page.activities}
            executionId={executionId}
            executionsQuery={page.executionsQuery}
            navigate={navigate}
            filters={page.executionFilters}
            onFilterChange={page.handleExecutionFilterChange}
            paginationFooterProps={page.executionPaginationFooterProps}
            onNodeClick={page.onCanvasNodeClick}
            selectedNodeId={page.selectedNodeId}
            selectedNodeName={page.selectedNodeName}
            onNodeSelect={page.onActivityRowSelect}
            currentApprovalNodeId={resolveWaitingNodeHighlightId(page.currentFormPrompt, page.currentApproval)}
          />
        </SynPageBody>
      </SynReactFlowViewportGuard>

      <CopyToEditorDialog
        isOpen={page.copyToEditorDialog.isOpen}
        onClose={page.copyToEditorDialog.close}
        onReplace={() => {
          page.copyToEditorDialog.close()
          if (execution?.workflow_id && executionId)
            detachPromise(
              navigate({
                to: '/workflow-builder/$workflowId',
                params: { workflowId: execution.workflow_id },
                search: { fromExecution: executionId },
              })
            )
        }}
        onFork={async () => {
          const id = await page.forkAsNewWorkflow()
          if (!id || !executionId) return
          page.copyToEditorDialog.close()
          detachPromise(
            navigate({
              to: '/workflow-builder/$workflowId',
              params: { workflowId: id },
              search: { linkExecution: executionId },
            })
          )
        }}
        isForkLoading={page.isForkLoading}
      />
    </SynPage>
  )
}
