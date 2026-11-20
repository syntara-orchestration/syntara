import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { workflowClient } from '../../../client'
import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import { useCursorPagination } from '../../../hooks/useCursorPagination'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { downloadVersionExport } from '../../../utils/downloadWorkflowExport'
import { processExistingWorkflow } from '../utils/processExistingWorkflow'

import { buildWorkflowVersionsQuery } from './buildWorkflowVersionsQuery'
import { useKafkaPublishGroups, type PreparedPublishOptions } from './useKafkaPublishGroups'
import { resolvePublishedVersionName } from './versionHistoryHelpers'

export type VersionStatus = 'draft' | 'published' | 'previously_published'

const VERSION_STATUSES: VersionStatus[] = ['draft', 'published', 'previously_published']
export function isVersionStatus(s: string): s is VersionStatus {
  return (VERSION_STATUSES as string[]).includes(s)
}

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

type UseVersionHistoryParams = {
  workflowId: string | null
  isNew: boolean
  onVersionUpdated?: (version: number) => void
}

export function useVersionHistory({ workflowId, isNew, onVersionUpdated }: UseVersionHistoryParams) {
  const [statusFilter, setStatusFilterState] = useState<VersionStatus[]>([])
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useAlerts()

  const {
    cursor: versionsCursor,
    perPage: versionsPerPage,
    resetPagination,
    getFooterProps: getVersionsPaginationFooterProps,
  } = useCursorPagination({
    limit: 20,
    extraParams: { workflow_id: workflowId ?? '' },
  })

  const setStatusFilter = useCallback(
    (statuses: VersionStatus[]) => {
      setStatusFilterState(statuses)
      resetPagination()
    },
    [resetPagination]
  )

  const versionsQueryParams = useMemo(
    () => buildWorkflowVersionsQuery(versionsPerPage, versionsCursor),
    [versionsCursor, versionsPerPage]
  )

  const versionsQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}/versions',
    {
      params: {
        path: { workflow_id: workflowId ?? '' },
        query: versionsQueryParams,
      },
    },
    {
      enabled: !!workflowId && !isNew,
    }
  )

  const restoreMutation = workflowClient.useMutation('post', '/workflows/{workflow_id}/versions/{version}/restore')
  const publishMutation = workflowClient.useMutation('post', '/workflows/{workflow_id}/versions/{version}/publish')
  const updateMetadataMutation = workflowClient.useMutation('patch', '/workflows/{workflow_id}/versions/{version}')

  const allVersions = versionsQuery.data?.resources
  const publishedVersionName = useMemo(() => resolvePublishedVersionName(allVersions), [allVersions])
  const filteredVersions = useMemo((): WorkflowVersion[] => {
    if (!allVersions) return []
    if (statusFilter.length === 0) return allVersions
    return (allVersions as WorkflowVersion[]).filter((v) => statusFilter.includes(v.status as VersionStatus))
  }, [allVersions, statusFilter])

  const paginationFooterProps = useMemo(
    (): PaginationFooterProps => getVersionsPaginationFooterProps(versionsQuery.data),
    [getVersionsPaginationFooterProps, versionsQuery.data]
  )

  const exportVersion = useCallback(
    (version: number) => {
      if (!workflowId) return
      detachPromise(
        downloadVersionExport(workflowId, version).catch((err: unknown) => {
          showError({ title: 'Export failed', description: getErrorMessage(err) })
        })
      )
    },
    [workflowId, showError]
  )

  const submitPublish = useCallback(
    (publishName?: string, changeDescription?: string, onSettled?: () => void, options?: PreparedPublishOptions) => {
      const version = options?.versionOverride
      if (!workflowId || version == null) return
      const submittedEditor = useWorkflowStore.getState()
      const submittedWorkflow = submittedEditor.currentWorkflow
      const wasDirty = submittedEditor.isDirty
      publishMutation.mutate(
        {
          params: { path: { workflow_id: workflowId, version } },
          body: {
            name: publishName ?? null,
            change_description: changeDescription ?? null,
            ...(options?.workflowDefinition ? { workflow_definition: options.workflowDefinition } : {}),
          },
        },
        {
          onSuccess: (data) => {
            showSuccess({ title: 'Version published' })
            const editor = useWorkflowStore.getState()
            if (
              data?.current_version != null &&
              data.version?.version === data.current_version &&
              data.version.workflow_definition &&
              !wasDirty &&
              !editor.isDirty &&
              editor.currentWorkflow === submittedWorkflow
            ) {
              const loaded = processExistingWorkflow(data)
              editor.loadWorkflowWithEdges(
                loaded.flattenedWorkflow,
                loaded.generatedEdges,
                loaded.nodePositions,
                data.project_id
              )
              editor.markClean()
              onVersionUpdated?.(data.current_version)
            }
            detachPromise(versionsQuery.refetch())
            detachPromise(
              queryClient.invalidateQueries({
                predicate: (q) =>
                  q.queryKey[0] === 'get' &&
                  typeof q.queryKey[1] === 'string' &&
                  q.queryKey[1].startsWith('/workflows'),
              })
            )
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to publish version', description: getErrorMessage(error) })
          },
          onSettled,
        }
      )
    },
    [workflowId, publishMutation, versionsQuery, queryClient, showSuccess, showError, onVersionUpdated]
  )

  const publication = useKafkaPublishGroups({
    workflowId,
    getDefinition: () => undefined,
    submit: submitPublish,
  })
  const publishVersion = (version: number, name?: string, description?: string, onSettled?: () => void) =>
    publication.publish(name, description, onSettled, { versionOverride: version })

  const openInNewWindow = useCallback(
    (version: number) => {
      if (!workflowId) return
      window.open(`/workflow-builder/${workflowId}?version=${version}`, '_blank', 'noopener,noreferrer')
    },
    [workflowId]
  )

  const updateVersionMetadata = useCallback(
    (version: number, publishName: string | null, changeDescription: string | null) => {
      if (!workflowId) return
      updateMetadataMutation.mutate(
        {
          params: { path: { workflow_id: workflowId, version } },
          body: { name: publishName, change_description: changeDescription },
        },
        {
          onSuccess: () => {
            showSuccess({ title: 'Version updated' })
            detachPromise(versionsQuery.refetch())
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to update version', description: getErrorMessage(error) })
          },
        }
      )
    },
    [workflowId, updateMetadataMutation, versionsQuery, showSuccess, showError]
  )

  return {
    versionsQuery,
    filteredVersions,
    publishedVersionName,
    statusFilter,
    setStatusFilter,
    restoreMutation,
    exportVersion,
    openInNewWindow,
    publishVersion,
    publication: {
      groupConflicts: publication.groupConflicts,
      confirmGroups: publication.confirmGroups,
      cancelGroups: publication.cancelGroups,
    },
    isPublishing: publishMutation.isPending || publication.isCheckingGroups,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  }
}
