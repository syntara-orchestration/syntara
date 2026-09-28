import type { Activity, WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, type Dispatch } from 'react'

import { workflowClient } from '../../../client'
import { useDialogState } from '../../../hooks/useDialogState'
import type { AlertMessage } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { detachPromise } from '../../../utils/detachPromise'
import type { BuilderAction } from '../builderReducer'
import { formatHistoryDateTime } from '../historyDateUtils'
import type { EdgeConnection } from '../types/edge'
import { convertV2Definition, parseNodePositions } from '../utils/processExistingWorkflow'

import { useVersionHistory } from './useVersionHistory'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type V2Edge = { from: string; to: string; from_port?: string; to_port?: string }

type RestoreDialogItem = { version: number; dateTime: string }

type UseBuilderVersionHistoryParams = {
  workflowId: string | null
  isNew: boolean
  workflow: WorkflowWithVersion | undefined
  viewingVersion: number | null
  dispatch: Dispatch<BuilderAction>
  showSuccess: (options: AlertMessage) => void
  showError: (options: AlertMessage) => void
  expandAllEvent?: EventTarget
  searchParams: URLSearchParams
  setSearchParams: (params: URLSearchParams) => void
  onVersionUpdated?: (version: number) => void
}

function loadDefinitionIntoStore(
  workflowDef: Record<string, unknown>,
  loadWorkflowWithEdges: (
    def: WorkflowDefinition,
    edges: EdgeConnection[],
    positions?: Record<string, { x: number; y: number }>
  ) => void
) {
  const rawNodes = (workflowDef.nodes ?? []) as Array<Record<string, unknown>>
  const rawTriggers = (workflowDef.triggers ?? []) as Array<Record<string, unknown>>
  const v2Edges = (workflowDef.edges ?? []) as V2Edge[]

  const { flattenedActivities, edges, triggers } = convertV2Definition(rawNodes as Activity[], v2Edges, rawTriggers)
  const nodePositions = parseNodePositions([...rawNodes, ...rawTriggers])

  const flattenedWorkflow = {
    ...workflowDef,
    triggers,
    workflow: { activities: flattenedActivities },
  } as unknown as WorkflowDefinition

  loadWorkflowWithEdges(flattenedWorkflow, edges, nodePositions)
}

export function useBuilderVersionHistory({
  workflowId,
  isNew,
  workflow,
  viewingVersion,
  dispatch,
  showSuccess,
  showError,
  expandAllEvent,
  searchParams,
  setSearchParams,
  onVersionUpdated,
}: UseBuilderVersionHistoryParams) {
  const { loadWorkflowWithEdges, markClean } = useWorkflowStore()
  const queryClient = useQueryClient()
  const restoreDialog = useDialogState<RestoreDialogItem>()
  const {
    filteredVersions,
    publishedVersionName,
    statusFilter,
    setStatusFilter,
    exportVersion,
    openInNewWindow,
    publishVersion,
    restoreMutation,
    versionsQuery,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  } = useVersionHistory({ workflowId, isNew, onVersionUpdated })

  const viewedVersionQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}/versions/{version}',
    { params: { path: { workflow_id: workflowId ?? '', version: viewingVersion ?? 0 } } },
    { enabled: !!workflowId && viewingVersion !== null }
  )

  const isViewingVersion = viewingVersion !== null
  const viewedVersionDate = viewedVersionQuery.data?.created_at ?? null
  const viewedVersionStatus = viewedVersionQuery.data?.status ?? null
  const viewedVersionDescription = viewedVersionQuery.data?.change_description ?? null
  const viewedVersionName = viewedVersionQuery.data?.name ?? null
  const viewedVersionPublishedAt = viewedVersionQuery.data?.last_published_at ?? null
  const viewedVersionUnpublishedAt = viewedVersionQuery.data?.last_unpublished_at ?? null

  useEffect(() => {
    if (!isViewingVersion || !viewedVersionQuery.data?.workflow_definition) return
    const def = viewedVersionQuery.data.workflow_definition as unknown as Record<string, unknown>
    loadDefinitionIntoStore(def, loadWorkflowWithEdges)
    markClean()
    expandAllEvent?.dispatchEvent(new Event('expandAll'))
  }, [isViewingVersion, viewedVersionQuery.data, loadWorkflowWithEdges, markClean, expandAllEvent])

  const clearVersionParam = useCallback(() => {
    const params = new URLSearchParams(searchParams)
    params.delete('version')
    setSearchParams(params)
  }, [searchParams, setSearchParams])

  const handleExitVersionView = useCallback(() => {
    dispatch({ type: 'EXIT_VERSION_VIEW' })
    dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
    clearVersionParam()
    if (workflow?.version?.workflow_definition) {
      const def = workflow.version.workflow_definition as unknown as Record<string, unknown>
      loadDefinitionIntoStore(def, loadWorkflowWithEdges)
      markClean()
      expandAllEvent?.dispatchEvent(new Event('expandAll'))
    }
  }, [dispatch, workflow, loadWorkflowWithEdges, markClean, expandAllEvent, clearVersionParam])

  const handleConfirmRestore = useCallback(() => {
    if (!restoreDialog.item || !workflowId) return
    const versionToRestore = restoreDialog.item.version
    restoreMutation.mutate(
      { params: { path: { workflow_id: workflowId, version: versionToRestore } } },
      {
        onSuccess: (data) => {
          restoreDialog.close()
          dispatch({ type: 'EXIT_VERSION_VIEW' })
          dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
          clearVersionParam()
          if (data.version?.workflow_definition) {
            const def = data.version.workflow_definition as unknown as Record<string, unknown>
            loadDefinitionIntoStore(def, loadWorkflowWithEdges)
          }
          detachPromise(versionsQuery.refetch())
          detachPromise(
            queryClient.invalidateQueries({
              predicate: (q) =>
                q.queryKey[0] === 'get' && typeof q.queryKey[1] === 'string' && q.queryKey[1].startsWith('/workflows'),
            })
          )
          showSuccess({ title: 'Version restored', description: `Restored from version ${versionToRestore}` })
        },
        onError: () => {
          showError({ title: 'Failed to restore version' })
        },
      }
    )
  }, [
    restoreDialog,
    workflowId,
    restoreMutation,
    dispatch,
    loadWorkflowWithEdges,
    versionsQuery,
    queryClient,
    showSuccess,
    showError,
    clearVersionParam,
  ])

  const restoreDialogTitle = restoreDialog.item?.dateTime
    ? `Restore version from ${formatHistoryDateTime(restoreDialog.item.dateTime)}?`
    : ''

  return {
    filteredVersions,
    publishedVersionName,
    statusFilter,
    setStatusFilter,
    exportVersion,
    openInNewWindow,
    publishVersion,
    isViewingVersion,
    viewedVersionDate,
    viewedVersionStatus,
    viewedVersionDescription,
    viewedVersionName,
    viewedVersionPublishedAt,
    viewedVersionUnpublishedAt,
    handleExitVersionView,
    handleConfirmRestore,
    restoreDialog,
    restoreDialogTitle,
    restoreMutation,
    versionsQuery,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  }
}
