import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { workflowClient } from '../../client'
import type { DialogState } from '../../hooks/useDialogState'
import { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { usePublishWorkflow } from '../builder/hooks/usePublishWorkflow'
import { PublishWorkflowDialog } from '../builder/PublishWorkflowDialog'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type PendingPublishReview = {
  workflow: Workflow
  publishName?: string
  description?: string
  review: WorkflowAPI.components['schemas']['BreakingChangesResponse']
}

type Props = Readonly<{
  publishDialog: DialogState<Workflow>
  isPublishing: boolean
  onPublishWorkflow: (workflow: Workflow, publishName?: string, description?: string) => void
}>

export function WorkflowPublishDialog({ publishDialog, isPublishing, onPublishWorkflow }: Props) {
  const { showError } = useAlerts()
  const [pendingReview, setPendingReview] = useState<PendingPublishReview | null>(null)
  const workflow = publishDialog.item
  const workflowQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    { params: { path: { workflow_id: workflow?.id ?? '' } } },
    { enabled: publishDialog.isOpen && Boolean(workflow?.id) }
  )
  const publishReview = usePublishWorkflow({
    workflowId: workflow?.id ?? null,
    currentVersion: workflow?.current_version,
    workflowName: workflow?.name,
    workflowDescription: workflow?.description ?? '',
  })

  const closeDialog = useCallback(() => {
    setPendingReview(null)
    publishDialog.close()
  }, [publishDialog])

  const reviewAndPublish = useCallback(
    (publishName?: string, description?: string) => {
      if (!workflow) return
      detachPromise(
        (async () => {
          try {
            const detail = workflowQuery.data ?? (await workflowQuery.refetch()).data
            const definition = detail?.version?.workflow_definition
            if (!definition) {
              showError({
                title: 'Failed to check output contract changes',
                description: 'Workflow definition is unavailable.',
              })
              return
            }
            const review = await publishReview.reviewOutputContract(definition)
            if (!review) return
            if (review.has_breaking_changes || (review.has_contract_changes && review.parent_workflows?.length)) {
              setPendingReview({ workflow, publishName, description, review })
              return
            }
            onPublishWorkflow(workflow, publishName, description)
          } catch (error) {
            showError({ title: 'Failed to check output contract changes', description: getErrorMessage(error) })
          }
        })()
      )
    },
    [onPublishWorkflow, publishReview, showError, workflow, workflowQuery]
  )

  const confirmPublish = useCallback(() => {
    if (!pendingReview) return
    const pending = pendingReview
    setPendingReview(null)
    onPublishWorkflow(pending.workflow, pending.publishName, pending.description)
  }, [onPublishWorkflow, pendingReview])

  return (
    <PublishWorkflowDialog
      isOpen={publishDialog.isOpen}
      isPublishing={isPublishing || publishReview.isPublishing}
      onClose={closeDialog}
      onPublish={reviewAndPublish}
      breakingChanges={pendingReview?.review.triggers ?? []}
      contractChanges={pendingReview?.review.contract_changes ?? []}
      parentWorkflows={pendingReview?.review.parent_workflows ?? []}
      onConfirmContractChanges={confirmPublish}
      onCancelBreakingChanges={() => setPendingReview(null)}
    />
  )
}
