import type { WorkflowAPI } from '@syntara/contracts'
import type { Query } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

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

function getCurrentWorkflowDefinition(
  workflowName: string | undefined,
  workflowDescription: string | undefined
): Record<string, unknown> | undefined {
  const { currentWorkflow, edges, nodePositions } = useWorkflowStore.getState()
  if (!currentWorkflow) return undefined
  const wf = currentWorkflow.workflow as { name?: string; description?: string } | undefined
  return buildWorkflowDefinition({
    workflowName: workflowName || String(wf?.name ?? ''),
    workflowDescription: workflowDescription || String(wf?.description ?? ''),
    activities: currentWorkflow.workflow.activities ?? [],
    triggers: currentWorkflow.triggers ?? [],
    edges,
    nodePositions,
  })
}

type PendingPublish = {
  publishName?: string
  description?: string
  onSettled?: () => void
  version: number
  expectedVersion?: number
  workflowDefinition?: Record<string, unknown>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

type UsePublishWorkflowOptions = {
  workflowId: string | null
  currentVersion: number | undefined
  workflowName?: string
  workflowDescription?: string
  expectedVersion?: number | null
  onConflict?: (info: ConflictInfo) => void
  onVersionUpdated?: (version: number) => void
}

export function usePublishWorkflow({
  workflowId,
  currentVersion,
  workflowName,
  workflowDescription,
  expectedVersion: optionsExpectedVersion,
  onConflict,
  onVersionUpdated,
}: UsePublishWorkflowOptions) {
  const queryClient = useQueryClient()
  const { showSuccess, showError, showWarning } = useAlerts()
  const [breakingChanges, setBreakingChanges] = useState<WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]>(
    []
  )
  const [contractChanges, setContractChanges] = useState<WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]>(
    []
  )
  const [parentWorkflows, setParentWorkflows] = useState<WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]>(
    []
  )
  const [pendingPublish, setPendingPublish] = useState<PendingPublish | null>(null)

  const { mutate: publishMutation, isPending: isPublishing } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/versions/{version}/publish'
  )

  const { mutate: checkBreakingChangesMutation, isPending: isCheckingBreakingChanges } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/versions/{version}/check-breaking-changes'
  )

  const reviewOutputContract = useCallback(
    (workflowDefinition?: unknown) => {
      const candidate = workflowDefinition ?? getCurrentWorkflowDefinition(workflowName, workflowDescription)
      if (!workflowId || currentVersion == null || !isRecord(candidate)) return Promise.resolve(null)

      return new Promise<WorkflowAPI.components['schemas']['BreakingChangesResponse'] | null>((resolve) => {
        checkBreakingChangesMutation(
          {
            params: { path: { workflow_id: workflowId, version: currentVersion } },
            body: { workflow_definition: candidate },
          },
          {
            onSuccess: resolve,
            onError: (error: unknown) => {
              showError({ title: 'Could not check output contract changes', description: getErrorMessage(error) })
              resolve(null)
            },
          }
        )
      })
    },
    [workflowId, currentVersion, workflowName, workflowDescription, checkBreakingChangesMutation, showError]
  )

  const publishNow = useCallback(
    (pending: PendingPublish) => {
      publishMutation(
        {
          params: { path: { workflow_id: workflowId ?? '', version: pending.version } },
          body: {
            name: pending.publishName ?? null,
            change_description: pending.description ?? null,
            ...(pending.workflowDefinition ? { workflow_definition: pending.workflowDefinition } : {}),
            ...(pending.expectedVersion != null ? { expected_version: pending.expectedVersion } : {}),
          },
        },
        {
          onSuccess: (data) => {
            if (data.warning) {
              showWarning({ title: 'Workflow published with warnings', description: data.warning })
            } else {
              showSuccess({ title: 'Workflow published' })
            }
            if (useWorkflowStore.getState().isDirty) useWorkflowStore.getState().markClean()
            if (data?.current_version != null) onVersionUpdated?.(data.current_version)
            detachPromise(queryClient.invalidateQueries({ predicate: isWorkflowQuery }))
          },
          onError: (error: unknown) => {
            if (isWorkflowVersionConflictError(error) && onConflict) {
              onConflict(extractVersionConflictInfo(error))
              return
            }
            showError({ title: 'Failed to publish workflow', description: getErrorMessage(error) })
          },
          onSettled: pending.onSettled,
        }
      )
    },
    [workflowId, publishMutation, showWarning, showSuccess, onVersionUpdated, queryClient, onConflict, showError]
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

      const workflowDefinition = getCurrentWorkflowDefinition(workflowName, workflowDescription)
      const expectedVersion = callOptions?.expectedVersionOverride ?? optionsExpectedVersion
      const pending: PendingPublish = {
        publishName,
        description,
        onSettled,
        version: versionToPublish,
        workflowDefinition,
        ...(expectedVersion != null ? { expectedVersion } : {}),
      }
      if (!workflowDefinition) {
        publishNow(pending)
        return
      }
      setBreakingChanges([])
      setContractChanges([])
      setParentWorkflows([])
      setPendingPublish(pending)
      detachPromise(
        reviewOutputContract(workflowDefinition).then((response) => {
          if (!response) {
            setPendingPublish(null)
            return
          }
          setBreakingChanges(response.triggers)
          setContractChanges(response.contract_changes ?? [])
          setParentWorkflows(response.parent_workflows ?? [])
          if (response.has_breaking_changes || (response.has_contract_changes && response.parent_workflows?.length)) {
            return
          }
          setPendingPublish(null)
          publishNow(pending)
        })
      )
    },
    [
      workflowId,
      currentVersion,
      workflowName,
      workflowDescription,
      optionsExpectedVersion,
      reviewOutputContract,
      publishNow,
    ]
  )

  const confirmPublish = useCallback(() => {
    if (!pendingPublish) return
    const pending = pendingPublish
    setBreakingChanges([])
    setContractChanges([])
    setParentWorkflows([])
    setPendingPublish(null)
    publishNow(pending)
  }, [pendingPublish, publishNow])

  const cancelBreakingChangeWarning = useCallback(() => {
    setBreakingChanges([])
    setContractChanges([])
    setParentWorkflows([])
    setPendingPublish(null)
  }, [])

  return {
    publish,
    isPublishing: isPublishing || isCheckingBreakingChanges,
    isCheckingBreakingChanges,
    breakingChanges,
    contractChanges,
    parentWorkflows,
    confirmPublish,
    cancelBreakingChangeWarning,
    reviewOutputContract,
  }
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
