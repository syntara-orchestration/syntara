import { TriggerTypeEnum } from '@syntara/contracts'
import { useMemo } from 'react'

import { workflowClient } from '../../../client'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'

type TriggerLike = { id?: string | null; type?: string | null }

export type RemovedSubworkflowTriggers = {
  /** Subworkflow Trigger node ids present in the published version but absent from the draft. */
  removedTriggerNodeIds: string[]
  /** True while the published-vs-draft diff is still resolving; the removal set is not yet known. */
  isLoading: boolean
  /** True if the diff could not be resolved; the removal set is unverified. */
  isError: boolean
}

function subworkflowTriggerIds(triggers: readonly TriggerLike[] | undefined): Set<string> {
  const ids = new Set<string>()
  for (const trigger of triggers ?? []) {
    if (trigger.type === TriggerTypeEnum.SUBWORKFLOW_TRIGGER && trigger.id) {
      ids.add(trigger.id)
    }
  }
  return ids
}

/**
 * Subworkflow Trigger node ids that this publish would remove: present in the currently published
 * version but absent from the proposed (draft) definition. Also reports whether that diff is still
 * loading or failed, so a caller never treats "not yet known" as "nothing removed" and publishes
 * before the dependency impact has been verified.
 *
 * Enabled only while the publish dialog is open so the two version reads are not made eagerly.
 */
export function useRemovedSubworkflowTriggerIds(
  workflowId: string | undefined,
  enabled: boolean
): RemovedSubworkflowTriggers {
  const draftTriggers = useWorkflowStore((state) => state.currentWorkflow?.triggers)

  const workflowQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    { params: { path: { workflow_id: workflowId ?? '' } } },
    { enabled: enabled && !!workflowId }
  )
  const publishedVersionNumber = workflowQuery.data?.published_version_number ?? null

  const publishedVersionQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}/versions/{version}',
    { params: { path: { workflow_id: workflowId ?? '', version: publishedVersionNumber ?? 0 } } },
    { enabled: enabled && !!workflowId && publishedVersionNumber != null }
  )

  const removedTriggerNodeIds = useMemo(() => {
    if (publishedVersionNumber == null) return []
    const publishedDefinition = publishedVersionQuery.data?.workflow_definition as
      { triggers?: TriggerLike[] } | undefined
    const publishedIds = subworkflowTriggerIds(publishedDefinition?.triggers)
    const draftIds = subworkflowTriggerIds(draftTriggers)
    return [...publishedIds].filter((id) => !draftIds.has(id))
  }, [publishedVersionNumber, publishedVersionQuery.data, draftTriggers])

  // The published-version read only matters when the workflow has a published version; a workflow
  // with none removes nothing, so that query stays disabled and does not count toward loading/error.
  const needsPublishedVersion = publishedVersionNumber != null
  const isLoading =
    enabled && !!workflowId && (workflowQuery.isLoading || (needsPublishedVersion && publishedVersionQuery.isLoading))
  const isError =
    enabled && !!workflowId && (workflowQuery.isError || (needsPublishedVersion && publishedVersionQuery.isError))

  return { removedTriggerNodeIds, isLoading, isError }
}
