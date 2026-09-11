import { useMemo } from 'react'

import { workflowClient } from '../../../client'
import { formatDateTime } from '../../../utils/dateUtils'

type UseIsCurrentVersionReturn = {
  isCurrentVersion: boolean
  versionLabel: string
  isLoading: boolean
}

export function useIsCurrentVersion(
  workflowId: string | undefined,
  workflowVersionId: string | undefined,
  enabled: boolean
): UseIsCurrentVersionReturn {
  // `enabled` guarantees workflowId is defined when the query runs.
  const workflowQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    { params: { path: { workflow_id: workflowId ?? '' } } },
    { enabled: enabled && !!workflowId }
  )

  const versionsQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}/versions',
    { params: { path: { workflow_id: workflowId ?? '' } } },
    { enabled: enabled && !!workflowId && !!workflowVersionId }
  )

  return useMemo((): UseIsCurrentVersionReturn => {
    if (!workflowQuery.data?.version || !workflowVersionId) {
      return { isCurrentVersion: true, versionLabel: '', isLoading: workflowQuery.isLoading || versionsQuery.isLoading }
    }

    const currentVersionId = workflowQuery.data.version.id
    const isCurrentVersion = currentVersionId === workflowVersionId

    if (isCurrentVersion) {
      return { isCurrentVersion: true, versionLabel: '', isLoading: false }
    }

    const executionVersion = versionsQuery.data?.resources?.find((v) => v.id === workflowVersionId)

    const versionLabel = executionVersion
      ? (executionVersion.name ?? formatDateTime(executionVersion.created_at))
      : 'a previous version'

    return { isCurrentVersion: false, versionLabel, isLoading: versionsQuery.isLoading }
  }, [workflowQuery.data, workflowQuery.isLoading, versionsQuery.data, versionsQuery.isLoading, workflowVersionId])
}
