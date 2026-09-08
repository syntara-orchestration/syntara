import type { Query } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { workflowClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { extractVersionConflictInfo, getErrorMessage, isWorkflowVersionConflictError } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { buildWorkflowDefinition } from '../utils/workflowDefinitionBuilder'
import type { ConflictInfo } from '../VersionConflictDialog'

function isWorkflowQuery(query: Query): boolean {
  return (
    query.queryKey[0] === 'get' && typeof query.queryKey[1] === 'string' && query.queryKey[1].startsWith('/workflows')
  )
}

function getDirtyWorkflowDefinition(
  workflowName: string | undefined,
  workflowDescription: string | undefined
): Record<string, unknown> | undefined {
  const { currentWorkflow, isDirty, edges, nodePositions } = useWorkflowStore.getState()
  if (!isDirty || !currentWorkflow) return undefined
  const wf = currentWorkflow.workflow as { name?: string; description?: string } | undefined
  return buildWorkflowDefinition(
    workflowName || String(wf?.name ?? ''),
    workflowDescription || String(wf?.description ?? ''),
    currentWorkflow.workflow.activities ?? [],
    currentWorkflow.triggers ?? [],
    { edges, nodePositions }
  ) as unknown as Record<string, unknown>
}

type UsePublishWorkflowOptions = {
  expectedVersion?: number | null
  onConflict?: (info: ConflictInfo) => void
  onVersionUpdated?: (version: number) => void
}

export function usePublishWorkflow(
  workflowId: string | null,
  currentVersion: number | undefined,
  workflowName?: string,
  workflowDescription?: string,
  options?: UsePublishWorkflowOptions
) {
  const queryClient = useQueryClient()
  const { showSuccess, showError, showWarning } = useAlerts()

  const { mutate: publishMutation, isPending: isPublishing } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/versions/{version}/publish'
  )

  const publish = useCallback(
    (
      publishName?: string,
      description?: string,
      onSettled?: () => void,
      callOptions?: { expectedVersionOverride?: number; versionOverride?: number }
    ) => {
      const versionToPublish = callOptions?.versionOverride ?? currentVersion
      if (!workflowId || versionToPublish == null) return

      const workflowDefinition = getDirtyWorkflowDefinition(workflowName, workflowDescription)
      const expectedVersion = callOptions?.expectedVersionOverride ?? options?.expectedVersion
      publishMutation(
        {
          params: { path: { workflow_id: workflowId, version: versionToPublish } },
          body: {
            name: publishName ?? null,
            change_description: description ?? null,
            ...(workflowDefinition ? { workflow_definition: workflowDefinition } : {}),
            ...(expectedVersion != null ? { expected_version: expectedVersion } : {}),
          } as { name: string | null; change_description: string | null },
        },
        {
          onSuccess: (data) => {
            if (data.warning) {
              showWarning({
                title: 'Workflow published with warnings',
                description: data.warning,
              })
            } else {
              showSuccess({ title: 'Workflow published' })
            }
            if (workflowDefinition) useWorkflowStore.getState().markClean()
            if (data?.current_version != null) {
              options?.onVersionUpdated?.(data.current_version)
            }
            detachPromise(queryClient.invalidateQueries({ predicate: isWorkflowQuery }))
          },
          onError: (error: unknown) => {
            if (isWorkflowVersionConflictError(error) && options?.onConflict) {
              options.onConflict(extractVersionConflictInfo(error))
              return
            }
            showError({ title: 'Failed to publish workflow', description: getErrorMessage(error) })
          },
          onSettled,
        }
      )
    },
    [
      workflowId,
      currentVersion,
      workflowName,
      workflowDescription,
      options,
      publishMutation,
      queryClient,
      showSuccess,
      showError,
      showWarning,
    ]
  )

  return { publish, isPublishing }
}

export function useUnpublishWorkflow(workflowId: string | null) {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useAlerts()

  const { mutate: unpublishMutation, isPending: isUnpublishing } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/unpublish'
  )

  const unpublish = useCallback(() => {
    if (!workflowId) return

    unpublishMutation(
      {
        params: { path: { workflow_id: workflowId } },
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Workflow unpublished' })
          detachPromise(queryClient.invalidateQueries({ predicate: isWorkflowQuery }))
        },
        onError: (error: unknown) => {
          showError({ title: 'Failed to unpublish workflow', description: getErrorMessage(error) })
        },
      }
    )
  }, [workflowId, unpublishMutation, queryClient, showSuccess, showError])

  return { unpublish, isUnpublishing }
}
