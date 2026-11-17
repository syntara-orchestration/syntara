import { TriggerTypeEnum, WorkflowVersionStatusEnum, type WorkflowAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { workflowFetchClient } from '../../../client'
import { fetchAllPages, MAX_ITEMS, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type Version = WorkflowAPI.components['schemas']['WorkflowVersionRead']
type PublishedSource = { integrationId: string; topic: string; groupId?: string }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function publishedSource(versions: Version[], triggerId: string): PublishedSource | undefined {
  const latest = versions.reduce<Version | undefined>((selected, version) => {
    if (!version.last_published_at) return selected
    if (
      !selected?.last_published_at ||
      Date.parse(version.last_published_at) > Date.parse(selected.last_published_at)
    ) {
      return version
    }
    return selected
  }, undefined)
  const triggers = latest?.workflow_definition.triggers
  if (!Array.isArray(triggers)) return undefined
  const trigger: unknown = triggers.find((item: unknown) => isRecord(item) && item.id === triggerId)
  if (!isRecord(trigger) || trigger.type !== TriggerTypeEnum.EVENT_SUBSCRIBE || !isRecord(trigger.parameters)) {
    return undefined
  }
  const { integration_id: integrationId, topic, group_id: groupId } = trigger.parameters
  return typeof integrationId === 'string' && typeof topic === 'string'
    ? { integrationId, topic, groupId: typeof groupId === 'string' ? groupId : undefined }
    : undefined
}

/** Publication timestamps survive unpublishing and can identify the last projected source. */
export function useKafkaPublishedSource(workflowId?: string | null, triggerId?: string) {
  const enabled = Boolean(workflowId && triggerId)
  const query = useQuery({
    // Share the workflow prefix so publish/unpublish invalidation refreshes this query too.
    queryKey: ['get', '/workflows/{workflow_id}/versions', { workflowId, scope: 'kafka-consumer-settings' }],
    enabled,
    queryFn: async () => {
      if (!workflowId) throw new Error('Workflow ID is required')
      const versions = await fetchAllPages((cursor) =>
        workflowFetchClient.GET('/workflows/{workflow_id}/versions', {
          params: { path: { workflow_id: workflowId }, query: { limit: MAX_PAGE_SIZE, cursor } },
        })
      )
      if (versions.length >= MAX_ITEMS) throw new Error('Publication history exceeds the supported limit')
      if (
        versions.some(
          (version) =>
            (version.status !== undefined &&
              version.status !== WorkflowVersionStatusEnum.DRAFT &&
              !version.last_published_at) ||
            (version.last_published_at && !Number.isFinite(Date.parse(version.last_published_at)))
        )
      )
        throw new Error('Publication timestamps are unavailable. The consumer group cannot be edited safely.')
      return versions
    },
  })
  const source = useMemo(() => publishedSource(query.data ?? [], triggerId ?? ''), [query.data, triggerId])
  return {
    source,
    isError: query.isError,
    isSuccess: query.isSuccess,
    error: query.error,
    refetch: query.refetch,
    isChecking: enabled && (query.isPending || query.isFetching),
  }
}
