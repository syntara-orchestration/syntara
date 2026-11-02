import { TitleSizes } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useRef } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { executionsClient } from '../../client'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynReactFlowViewportGuard } from '../../components/layout/SynReactFlowViewportGuard'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDialogState } from '../../hooks/useDialogState'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'
import { canvasNodeIdFromApprovalNodeId } from '../approvals/approvalNodeId'
import type { WorkflowDefShape } from '../builder/ExecutionDetailsPanel'
import { useActivityNameMap } from '../builder/useActivityNameMap'
import type { ActivityState } from '../workflows/execution/types'
import { useExecutionStore, useExecutionWithLiveStatus } from '../workflows/stores/useExecutionStore'

import { ApprovalSidePanel } from './ApprovalSidePanel'
import { ExecutionDetailErrorStates } from './components/ExecutionDetailErrorStates'
import { CopyToEditorDialog } from './CopyToEditorDialog'
import { isExecutionCancellable } from './executionCancellable'
import { ExecutionDetailContent } from './ExecutionDetailContent'
import { ExecutionDetailHeaderToolbar, ExecutionDetailTitleRowAddons } from './ExecutionDetailPageHeaderParts'
import { executionDetailHasTitleRowExtras, executionDetailPageHeading } from './executionDetailPageHeaderTitle'
import { executionRefetchInterval } from './executionPolling'
import { useApprovalNavigation } from './hooks/useApprovalNavigation'
import { useExecutionApprovalPanel } from './hooks/useExecutionApprovalPanel'
import { useExecutionRunHistory } from './hooks/useExecutionRunHistory'
import { useExecutionStepClick } from './hooks/useExecutionStepClick'
import { useExecutionStreaming, useSyncActivityStore } from './hooks/useExecutionStreaming'
import { useExecutionWorkflow } from './hooks/useExecutionWorkflow'
import { useForkWorkflow } from './hooks/useForkWorkflow'
import { useRetryFromFailurePanel } from './hooks/useRetryFromFailurePanel'

/** Returns true when the page should render a fallback (missing ID, loading, or error) instead of the main content. */
function shouldShowFallbackState(
  executionId: string | undefined,
  query: { isLoading: boolean; error: unknown }
): boolean {
  return !executionId || query.isLoading || !!query.error
}

/** Reset execution store only when the execution ID actually changes. */
function useResetOnExecutionChange(executionId: string | undefined) {
  const { reset } = useExecutionStore.getState()
  const prevExecutionIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (executionId && prevExecutionIdRef.current !== executionId) {
      reset()
    }
    prevExecutionIdRef.current = executionId ?? null
  }, [executionId, reset])
}

/** Build activity name and type maps from the retained workflow definition. */
function useActivityMapsForExecution(
  workflowDefinition: WorkflowDefShape | undefined | null,
  activities: (ActivityData | ActivityExecution)[]
): { nameMap: Map<string, string>; typeMap: Map<string, string> } {
  const activityStates = useMemo(() => {
    const map = new Map<string, ActivityState>()
    for (const activity of activities) {
      const activityId = 'activity_id' in activity ? activity.activity_id : null
      if (activityId) {
        map.set(activityId, { activityId, status: activity.status } as ActivityState)
      }
    }
    return map
  }, [activities])

  const { nameMap, typeMap } = useActivityNameMap(workflowDefinition, activityStates)
  return { nameMap, typeMap }
}

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

// Inner component that has access to React Flow context
export default function ExecutionDetail() {
  const executionsDocLink = useDocLink('executions')
  const { executionId }: { executionId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const searchParams = useRouterState({ select: (s) => s.location.searchStr.replace(/^\?/, '') })

  useResetOnExecutionChange(executionId)

  const executionQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    {
      params: {
        path: { execution_id: executionId ?? '' },
        query: {
          include: 'workflow_definition,activities',
        },
      },
      enabled: !!executionId,
    },
    { refetchInterval: executionRefetchInterval }
  )

  const execution = useExecutionWithLiveStatus(executionQuery.data)

  useExecutionStreaming(executionId, execution)

  const historyCardOpen = useMemo(() => {
    const params = new URLSearchParams(searchParams)
    return params.get('history') === 'open'
  }, [searchParams])

  const { executionFilters, handleExecutionFilterChange, executionsQuery, executionPaginationFooterProps } =
    useExecutionRunHistory(execution?.workflow_id)

  const { workflow, activities } = useExecutionWorkflow(execution)

  useSyncActivityStore(execution, activities)

  const { nameMap: activityNameMap, typeMap: activityTypeMap } = useActivityMapsForExecution(
    execution?.workflow_definition,
    activities
  )

  const stepClick = useExecutionStepClick(executionId)
  const { approvals, currentIndex, currentApproval, isApprovalLoading, handleNodeClick, navigateToIndex } = stepClick
  const { selectedStepId, selectedStepName, selectStep } = stepClick
  const approval = useExecutionApprovalPanel(
    executionId,
    searchParams,
    stepClick,
    execution?.workflow_definition ?? undefined
  )
  const approvalNavigation = useApprovalNavigation(currentIndex, navigateToIndex, approvals)
  const copyToEditorDialog = useDialogState<void>()
  const retryPanel = useRetryFromFailurePanel({
    navigate,
    executionId,
    historyCardOpen,
    closeApprovalPanel: approval.close,
  })
  const isCancellable = isExecutionCancellable(execution?.status)

  const { forkAsNewWorkflow, isForkLoading } = useForkWorkflow({
    workflowDefinition: execution?.workflow_definition,
    workflowName: workflow?.name ?? 'Workflow',
    projectId: execution?.project_id,
  })

  const toggleHistoryCard = () => {
    const willOpen = !historyCardOpen
    if (willOpen) {
      approval.close()
      retryPanel.closeWithoutFocus()
    }
    detachPromise(
      navigate({
        to: '/executions/$executionId',
        params: { executionId },
        search: (prev: Record<string, unknown>) => ({ ...prev, history: willOpen ? 'open' : 'closed' }),
      })
    )
  }

  if (shouldShowFallbackState(executionId, executionQuery)) {
    return (
      <ExecutionDetailErrorStates
        executionId={executionId}
        isLoading={executionQuery.isLoading}
        error={executionQuery.error}
        onRetry={executionQuery.refetch}
      />
    )
  }

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
              showApprovalActionStrip={Boolean(currentApproval ?? isApprovalLoading)}
              isApprovalLoading={isApprovalLoading}
              isApprovalPanelOpen={approval.panelOpen}
              onReviewClick={approval.open}
              historyCardOpen={historyCardOpen}
              onToggleHistory={toggleHistoryCard}
              onBackToEditor={() => {
                if (execution?.workflow_id) {
                  detachPromise(
                    navigate({ to: '/workflow-builder/$workflowId', params: { workflowId: execution.workflow_id } })
                  )
                }
              }}
              onCopyToEditor={() => copyToEditorDialog.open(undefined)}
              isCancellable={isCancellable}
              executionId={executionId}
              execution={execution}
              onRetryFromFailureClick={retryPanel.open}
              isRetryMode={retryPanel.isOpen}
            />
          }
        />
        <SynPageBody>
          <ExecutionDetailContent
            key={executionId}
            historyCardOpen={historyCardOpen && !approval.panelOpen && !retryPanel.isOpen}
            approvalPanel={
              !retryPanel.isOpen && approval.panelOpen && currentApproval ? (
                <ApprovalSidePanel
                  approval={currentApproval}
                  message={approval.approvalMessage}
                  activityNameMap={activityNameMap}
                  onClose={approval.close}
                  onDecisionSubmitted={approval.dismiss}
                  onNavigate={(path) => detachPromise(navigate({ to: path }))}
                  currentIndex={currentIndex}
                  totalCount={approvals.length}
                  hasPrev={approvalNavigation.hasPrev}
                  hasNext={approvalNavigation.hasNext}
                  onNavigatePrev={approvalNavigation.navigatePrev}
                  onNavigateNext={approvalNavigation.navigateNext}
                />
              ) : undefined
            }
            retryPanelOpen={retryPanel.isOpen}
            activityNameMap={activityNameMap}
            activityTypeMap={activityTypeMap}
            onRetryPanelClose={retryPanel.close}
            workflow={workflow}
            execution={execution}
            activities={activities}
            executionId={executionId}
            executionsQuery={executionsQuery}
            navigate={navigate}
            filters={executionFilters}
            onFilterChange={handleExecutionFilterChange}
            paginationFooterProps={executionPaginationFooterProps}
            onNodeClick={handleNodeClick}
            selectedStepId={selectedStepId}
            selectedStepName={selectedStepName}
            onStepSelect={selectStep}
            currentApprovalNodeId={
              currentApproval ? canvasNodeIdFromApprovalNodeId(currentApproval.approval_node_id) : undefined
            }
          />
        </SynPageBody>
      </SynReactFlowViewportGuard>

      <CopyToEditorDialog
        isOpen={copyToEditorDialog.isOpen}
        onClose={copyToEditorDialog.close}
        onReplace={() => {
          copyToEditorDialog.close()
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
          const id = await forkAsNewWorkflow()
          if (!id || !executionId) return
          copyToEditorDialog.close()
          detachPromise(
            navigate({
              to: '/workflow-builder/$workflowId',
              params: { workflowId: id },
              search: { linkExecution: executionId },
            })
          )
        }}
        isForkLoading={isForkLoading}
      />
    </SynPage>
  )
}
