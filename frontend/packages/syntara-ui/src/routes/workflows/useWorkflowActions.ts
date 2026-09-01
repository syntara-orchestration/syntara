import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback } from 'react'

import { executionsFetchClient, workflowClient } from '../../client'
import type { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'

import { resolveWorkflowRunTrigger } from './resolveWorkflowRunTrigger'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type UseWorkflowActionsOptions = {
  showSuccess: ReturnType<typeof useAlerts>['showSuccess']
  showError: ReturnType<typeof useAlerts>['showError']
  onNavigate: (path: string) => void
  onRefetch: () => void
  onDeleteSettled?: () => void
  onPublishSettled?: () => void
  onUnpublishSettled?: () => void
}

export function useWorkflowActions({
  showSuccess,
  showError,
  onNavigate,
  onRefetch,
  onDeleteSettled,
  onPublishSettled,
  onUnpublishSettled,
}: UseWorkflowActionsOptions) {
  const { mutate: deleteWorkflow, isPending: isDeleting } = workflowClient.useMutation(
    'delete',
    '/workflows/{workflow_id}'
  )
  const { mutate: publishWorkflow, isPending: isPublishing } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/versions/{version}/publish'
  )
  const { mutate: unpublishWorkflow } = workflowClient.useMutation('post', '/workflows/{workflow_id}/unpublish')

  const handleRunWorkflow = useCallback(
    async (workflow: Workflow, inputData: Record<string, unknown> = {}, triggerNodeId?: string) => {
      if (!workflow.id) return

      let resolvedTriggerNodeId = triggerNodeId
      if (!resolvedTriggerNodeId) {
        const trigger = await resolveWorkflowRunTrigger(workflow)
        if (!trigger) {
          showError({ title: 'Cannot run workflow', description: 'Workflow has no triggers configured' })
          return
        }
        resolvedTriggerNodeId = trigger.triggerNodeId
      }

      const { data, error } = await executionsFetchClient.POST('/executions', {
        body: {
          workflow_id: workflow.id,
          input_data: inputData,
          trigger_node_id: resolvedTriggerNodeId,
          use_published: true,
        },
      })
      if (error || !data?.id) {
        showError({
          title: 'Failed to run workflow',
          description: `Failed to start workflow "${workflow.name}": ${getErrorMessage(error)}`,
        })
      } else {
        onNavigate(`/executions/${data.id}`)
      }
    },
    [onNavigate, showError]
  )

  const handleDeleteWorkflow = useCallback(
    (workflow: Workflow) => {
      if (!workflow?.id) return

      deleteWorkflow(
        { params: { path: { workflow_id: workflow.id } } },
        {
          onSuccess: () => {
            showSuccess({ title: 'Workflow deleted', description: `Workflow "${workflow.name}" has been deleted.` })
            onRefetch()
          },
          onError: (error: unknown) => {
            showError({
              title: 'Failed to delete workflow',
              description: `Failed to delete workflow "${workflow.name}": ${getErrorMessage(error)}`,
            })
          },
          onSettled: () => {
            onDeleteSettled?.()
          },
        }
      )
    },
    [deleteWorkflow, showSuccess, showError, onRefetch, onDeleteSettled]
  )

  const handlePublishWorkflow = useCallback(
    (workflow: Workflow, publishName?: string, description?: string) => {
      if (!workflow?.id || !workflow.current_version) return

      publishWorkflow(
        {
          params: { path: { workflow_id: workflow.id, version: workflow.current_version } },
          body: { name: publishName ?? null, change_description: description ?? null },
        },
        {
          onSuccess: () => {
            showSuccess({ title: 'Workflow published' })
            onRefetch()
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to publish workflow', description: getErrorMessage(error) })
          },
          onSettled: () => {
            onPublishSettled?.()
          },
        }
      )
    },
    [publishWorkflow, showSuccess, showError, onRefetch, onPublishSettled]
  )

  const handleUnpublishWorkflow = useCallback(
    (workflow: Workflow) => {
      if (!workflow?.id) return

      unpublishWorkflow(
        { params: { path: { workflow_id: workflow.id } } },
        {
          onSuccess: () => {
            showSuccess({ title: 'Workflow unpublished' })
            onRefetch()
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to unpublish workflow', description: getErrorMessage(error) })
          },
          onSettled: () => {
            onUnpublishSettled?.()
          },
        }
      )
    },
    [unpublishWorkflow, showSuccess, showError, onRefetch, onUnpublishSettled]
  )

  return {
    handleRunWorkflow,
    handleDeleteWorkflow,
    handlePublishWorkflow,
    handleUnpublishWorkflow,
    isDeleting,
    isPublishing,
  }
}
