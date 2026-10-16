import type { ExecutionsAPI } from '@syntara/contracts'
import { useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import { useEffect, useMemo, useRef } from 'react'

import { executionsClient } from '../../../client'
import { useDialogState } from '../../../hooks/useDialogState'
import { useActivityNameMap } from '../../builder/useActivityNameMap'
import type { WorkflowDefShape } from '../../builder/useActivityNameMap'
import type { ActivityState } from '../../workflows/execution/types'
import { useExecutionStore, useExecutionWithLiveStatus } from '../../workflows/stores/useExecutionStore'
import { isExecutionCancellable } from '../executionCancellable'
import { executionRefetchInterval } from '../executionPolling'

import { useExecutionDetailPanelState } from './useExecutionDetailPanelState'
import { useExecutionNodeClick } from './useExecutionNodeClick'
import { useExecutionRunHistory } from './useExecutionRunHistory'
import { useExecutionStreaming, useSyncActivityStore } from './useExecutionStreaming'
import { useExecutionWorkflow } from './useExecutionWorkflow'
import { useForkWorkflow } from './useForkWorkflow'

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

function useActivityNamesForExecution(
  workflowDefinition: WorkflowDefShape | undefined | null,
  activities: (ActivityData | ActivityExecution)[]
): Map<string, string> {
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

  const { nameMap } = useActivityNameMap(workflowDefinition, activityStates)
  return nameMap
}

/** Data and handlers for the execution detail page shell (canvas, side panels, run history). */
export function useExecutionDetailPageModel() {
  const { executionId }: { executionId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const searchParams = useRouterState({ select: (s) => s.location.searchStr.replace(/^\?/, '') })

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

  const activityNameMap = useActivityNamesForExecution(execution?.workflow_definition, activities)

  const nodeClick = useExecutionNodeClick(executionId, execution?.workflow_definition ?? undefined)
  const {
    approvals,
    currentIndex,
    currentApproval,
    isApprovalLoading,
    formPrompts,
    formPromptIndex,
    currentFormPrompt,
    isFormPromptLoading,
    selectedNodeId,
    selectedNodeName,
  } = nodeClick

  const panelState = useExecutionDetailPanelState({
    executionId,
    searchParams,
    execution,
    workflow,
    historyCardOpen,
    navigate,
    nodeClick,
  })

  const copyToEditorDialog = useDialogState<void>()
  const isCancellable = isExecutionCancellable(execution?.status)

  const { forkAsNewWorkflow, isForkLoading } = useForkWorkflow({
    workflowDefinition: execution?.workflow_definition,
    workflowName: workflow?.name ?? 'Workflow',
    projectId: execution?.project_id,
  })

  return {
    executionId,
    navigate,
    executionQuery,
    execution,
    historyCardOpen,
    executionFilters,
    handleExecutionFilterChange,
    executionsQuery,
    executionPaginationFooterProps,
    workflow,
    activities,
    activityNameMap,
    currentApproval,
    isApprovalLoading,
    approval: panelState.approval,
    formPromptPanel: panelState.formPromptPanel,
    currentFormPrompt,
    isFormPromptLoading,
    formPrompts,
    formPromptIndex,
    formPromptNavigation: panelState.formPromptNavigation,
    approvalNavigation: panelState.approvalNavigation,
    currentIndex,
    approvals,
    copyToEditorDialog,
    isCancellable,
    onCanvasNodeClick: panelState.onCanvasNodeClick,
    onActivityRowSelect: panelState.onActivityRowSelect,
    toggleHistoryCard: panelState.toggleHistoryCard,
    forkAsNewWorkflow,
    isForkLoading,
    selectedNodeId,
    selectedNodeName,
    hasOpenExecutionSidePanel: panelState.hasOpenExecutionSidePanel,
    workflowDefinitionForSidePanel: panelState.workflowDefinitionForSidePanel,
  }
}

/** Reset execution store only when the execution ID actually changes. */
export function useResetOnExecutionChange(executionId: string | undefined) {
  const { reset } = useExecutionStore.getState()
  const prevExecutionIdRef = useRef<string | null>(null)

  /* eslint-disable reactYouMightNotNeedAnEffect/no-event-handler -- store reset on route param change */
  useEffect(() => {
    if (executionId && prevExecutionIdRef.current !== executionId) {
      reset()
    }
    prevExecutionIdRef.current = executionId ?? null
  }, [executionId, reset])
  /* eslint-enable reactYouMightNotNeedAnEffect/no-event-handler */
}
