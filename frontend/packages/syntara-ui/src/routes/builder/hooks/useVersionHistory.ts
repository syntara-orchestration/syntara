import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { workflowClient } from '../../../client'
import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import { useCursorPagination } from '../../../hooks/useCursorPagination'
import { useAlerts, type AlertMessage } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { downloadVersionExport } from '../../../utils/downloadWorkflowExport'

import { buildWorkflowVersionsQuery } from './buildWorkflowVersionsQuery'
import { resolvePublishedVersionName } from './versionHistoryHelpers'

export type VersionStatus = 'draft' | 'published' | 'previously_published'

const VERSION_STATUSES: VersionStatus[] = ['draft', 'published', 'previously_published']
export function isVersionStatus(s: string): s is VersionStatus {
  return (VERSION_STATUSES as string[]).includes(s)
}

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']
type TriggerBreakingChanges = WorkflowAPI.components['schemas']['TriggerBreakingChanges']

type PendingVersionPublish = {
  version: number
  publishName?: string
  changeDescription?: string
  workflowDefinition: Record<string, unknown>
  onSettled?: () => void
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
  const checkBreakingChangesMutation = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/versions/{version}/check-breaking-changes'
  )
  const updateMetadataMutation = workflowClient.useMutation('patch', '/workflows/{workflow_id}/versions/{version}')
  const [breakingChanges, setBreakingChanges] = useState<TriggerBreakingChanges[]>([])
  const [pendingPublish, setPendingPublish] = useState<PendingVersionPublish | null>(null)

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
    (version: number) => downloadWorkflowVersion(workflowId, version, showError),
    [workflowId, showError]
  )

  const publishVersionNow = useCallback(
    (pending: PendingVersionPublish) => {
      publishMutation.mutate(
        {
          params: { path: { workflow_id: workflowId ?? '', version: pending.version } },
          body: {
            name: pending.publishName ?? null,
            change_description: pending.changeDescription ?? null,
          },
        },
        {
          onSuccess: (data) => {
            showSuccess({ title: 'Version published' })
            if (data?.current_version != null) {
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
          onSettled: pending.onSettled,
        }
      )
    },
    [workflowId, publishMutation, versionsQuery, queryClient, showSuccess, showError, onVersionUpdated]
  )

  const publishVersion = useCallback(
    (version: number, publishName?: string, changeDescription?: string, onSettled?: () => void) => {
      if (!workflowId) return
      const workflowDefinition = allVersions?.find((item) => item.version === version)?.workflow_definition
      if (!workflowDefinition) {
        showError({
          title: 'Failed to check output contract changes',
          description: 'Version definition is unavailable',
        })
        return
      }
      const pending: PendingVersionPublish = {
        version,
        publishName,
        changeDescription,
        workflowDefinition,
        onSettled,
      }
      setBreakingChanges([])
      setPendingPublish(pending)
      checkBreakingChangesMutation.mutate(
        {
          params: { path: { workflow_id: workflowId, version } },
          body: { workflow_definition: workflowDefinition },
        },
        {
          onSuccess: (response) => {
            if (response.has_breaking_changes) {
              setBreakingChanges(response.triggers)
              return
            }
            setPendingPublish(null)
            publishVersionNow(pending)
          },
          onError: (error: unknown) => {
            setPendingPublish(null)
            showError({ title: 'Failed to check output contract changes', description: getErrorMessage(error) })
          },
        }
      )
    },
    [workflowId, allVersions, checkBreakingChangesMutation, publishVersionNow, showError]
  )

  const confirmPublishVersion = useCallback(() => {
    if (!pendingPublish) return
    const pending = pendingPublish
    setBreakingChanges([])
    setPendingPublish(null)
    publishVersionNow(pending)
  }, [pendingPublish, publishVersionNow])

  const cancelBreakingChangeWarning = useCallback(() => {
    setBreakingChanges([])
    setPendingPublish(null)
  }, [])

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
    isPublishingVersion: publishMutation.isPending || checkBreakingChangesMutation.isPending,
    breakingChanges,
    confirmPublishVersion,
    cancelBreakingChangeWarning,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  }
}
