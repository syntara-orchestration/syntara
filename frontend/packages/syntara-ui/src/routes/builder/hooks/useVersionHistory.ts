import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useMemo, useState } from 'react'

import { workflowClient } from '../../../client'
import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import { useCursorPagination } from '../../../hooks/useCursorPagination'
import { useAlerts, type AlertMessage } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { downloadVersionExport } from '../../../utils/downloadWorkflowExport'

import { buildWorkflowVersionsQuery } from './buildWorkflowVersionsQuery'
import { useVersionHistoryPublishing } from './useVersionHistoryPublishing'
import { resolvePublishedVersionName } from './versionHistoryHelpers'

export type VersionStatus = 'draft' | 'published' | 'previously_published'

const VERSION_STATUSES: VersionStatus[] = ['draft', 'published', 'previously_published']
export function isVersionStatus(s: string): s is VersionStatus {
  return (VERSION_STATUSES as string[]).includes(s)
}

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

function openWorkflowVersion(workflowId: string | null, version: number): void {
  if (workflowId) window.open(`/workflow-builder/${workflowId}?version=${version}`, '_blank', 'noopener,noreferrer')
}

function downloadWorkflowVersion(
  workflowId: string | null,
  version: number,
  showError: (options: AlertMessage) => void
): void {
  if (!workflowId) return
  detachPromise(
    downloadVersionExport(workflowId, version).catch((err: unknown) => {
      showError({ title: 'Export failed', description: getErrorMessage(err) })
    })
  )
}

type UseVersionHistoryParams = {
  workflowId: string | null
  isNew: boolean
  onVersionUpdated?: (version: number) => void
}

export function useVersionHistory({ workflowId, isNew, onVersionUpdated }: UseVersionHistoryParams) {
  const [statusFilter, setStatusFilterState] = useState<VersionStatus[]>([])
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
  const updateMetadataMutation = workflowClient.useMutation('patch', '/workflows/{workflow_id}/versions/{version}')

  const allVersions = versionsQuery.data?.resources
  const publishActions = useVersionHistoryPublishing({
    workflowId,
    versions: allVersions,
    refetchVersions: versionsQuery.refetch,
    onVersionUpdated,
  })
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
    (version: number) => downloadWorkflowVersion(workflowId, version, showError),
    [workflowId, showError]
  )

  const openInNewWindow = useCallback((version: number) => openWorkflowVersion(workflowId, version), [workflowId])

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
    ...publishActions,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  }
}
