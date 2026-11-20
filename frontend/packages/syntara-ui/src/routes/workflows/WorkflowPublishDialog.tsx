import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useEffect, useState } from 'react'

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
  version: number
  publishedVersionId: string | null
  review: WorkflowAPI.components['schemas']['BreakingChangesResponse'] | null
}

type PublishReviewDialogState = Readonly<{
  isPublishDisabled: boolean
  isCheckingContractChanges: boolean
  breakingChanges: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  contractChanges: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  parentWorkflows: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
}>

type UseWorkflowOutputReviewProps = Readonly<{
  isOpen: boolean
  workflow: Workflow | null | undefined
  workflowDefinition: unknown
  version: number | undefined
  publishedVersionId: string | null
  isFetching: boolean
  isLoading: boolean
  error: unknown
  pendingReview: PendingPublishReview | null
  setPendingReview: (review: PendingPublishReview) => void
  reviewOutputContract: (
    definition: unknown
  ) => Promise<WorkflowAPI.components['schemas']['BreakingChangesResponse'] | null>
  showError: (alert: { title: string; description: string }) => void
}>

function isCurrentWorkflowReview(
  pendingReview: PendingPublishReview | null,
  workflow: Workflow | null | undefined,
  version: number | undefined,
  publishedVersionId: string | null
): boolean {
  return Boolean(
    workflow &&
    version != null &&
    pendingReview?.workflow.id === workflow.id &&
    pendingReview.version === version &&
    pendingReview.publishedVersionId === publishedVersionId
  )
}

function useWorkflowOutputReview({
  isOpen,
  workflow,
  workflowDefinition,
  version,
  publishedVersionId,
  isFetching,
  isLoading,
  error,
  pendingReview,
  setPendingReview,
  reviewOutputContract,
  showError,
}: UseWorkflowOutputReviewProps): boolean {
  const hasCurrentReview = isCurrentWorkflowReview(pendingReview, workflow, version, publishedVersionId)

  useEffect(() => {
    if (!isOpen || !workflow?.id || isFetching || isLoading) return

    if (!workflowDefinition || version == null) {
      showError({
        title: 'Failed to check output contract changes',
        description: getErrorMessage(error ?? 'Workflow definition is unavailable.'),
      })
      return
    }

    if (hasCurrentReview) return

    let isCurrent = true
    detachPromise(
      reviewOutputContract(workflowDefinition)
        .then((review) => {
          if (isCurrent) setPendingReview({ workflow, version, publishedVersionId, review })
        })
        .catch((reviewError: unknown) => {
          if (isCurrent) {
            showError({ title: 'Failed to check output contract changes', description: getErrorMessage(reviewError) })
            setPendingReview({ workflow, version, publishedVersionId, review: null })
          }
        })
    )

    return () => {
      isCurrent = false
    }
  }, [
    error,
    hasCurrentReview,
    isFetching,
    isLoading,
    isOpen,
    reviewOutputContract,
    setPendingReview,
    showError,
    version,
    publishedVersionId,
    workflow,
    workflowDefinition,
  ])

  return hasCurrentReview
}

function isWorkflowReviewInProgress({
  isOpen,
  workflowId,
  isFetching,
  isLoading,
  workflowDefinition,
  version,
  hasCurrentReview,
}: Readonly<{
  isOpen: boolean
  workflowId: string
  isFetching: boolean
  isLoading: boolean
  workflowDefinition: unknown
  version: number | undefined
  hasCurrentReview: boolean
}>): boolean {
  return Boolean(
    isOpen && workflowId && (isFetching || isLoading || (workflowDefinition && version != null && !hasCurrentReview))
  )
}

function getPublishReviewDialogState({
  isOpen,
  isPublishing,
  isReviewPublishing,
  hasCurrentReview,
  workflowId,
  workflowDefinition,
  version,
  isFetching,
  isLoading,
  pendingReview,
}: Readonly<{
  isOpen: boolean
  isPublishing: boolean
  isReviewPublishing: boolean
  hasCurrentReview: boolean
  workflowId: string
  workflowDefinition: unknown
  version: number | undefined
  isFetching: boolean
  isLoading: boolean
  pendingReview: PendingPublishReview | null
}>): PublishReviewDialogState & { isPublishing: boolean } {
  const isCheckingContractChanges = isWorkflowReviewInProgress({
    isOpen,
    workflowId,
    isFetching,
    isLoading,
    workflowDefinition,
    version,
    hasCurrentReview,
  })
  const review = pendingReview?.review
  const canPublish = hasCurrentReview && Boolean(workflowDefinition) && Boolean(review)

  return {
    isPublishing: isPublishing || isReviewPublishing,
    isPublishDisabled: !canPublish,
    isCheckingContractChanges,
    breakingChanges: review?.triggers ?? [],
    contractChanges: review?.contract_changes ?? [],
    parentWorkflows: review?.parent_workflows ?? [],
  }
}

function getPublishReviewOptions(workflow: Workflow | null | undefined) {
  return {
    workflowId: workflow?.id ?? null,
    currentVersion: workflow?.current_version,
    workflowName: workflow?.name,
    workflowDescription: workflow?.description ?? '',
  }
}

function useWorkflowDetailQuery(workflowId: string, isOpen: boolean) {
  return workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    { params: { path: { workflow_id: workflowId } } },
    { enabled: isOpen && workflowId.length > 0 }
  )
}

function usePublishReviewedVersion(
  canPublish: boolean,
  pendingReview: PendingPublishReview | null,
  onPublishWorkflow: Props['onPublishWorkflow']
) {
  return useCallback(
    (publishName?: string, description?: string) => {
      if (!canPublish || !pendingReview) return
      onPublishWorkflow(pendingReview.workflow, pendingReview.version, publishName, description)
    },
    [canPublish, onPublishWorkflow, pendingReview]
  )
}

type Props = Readonly<{
  publishDialog: DialogState<Workflow>
  isPublishing: boolean
  onPublishWorkflow: (workflow: Workflow, version: number, publishName?: string, description?: string) => void
}>

export function WorkflowPublishDialog({ publishDialog, isPublishing, onPublishWorkflow }: Props) {
  const { showError } = useAlerts()
  const [pendingReview, setPendingReview] = useState<PendingPublishReview | null>(null)
  const workflow = publishDialog.item
  const workflowId = workflow?.id ?? ''
  const workflowQuery = useWorkflowDetailQuery(workflowId, publishDialog.isOpen)
  const { reviewOutputContract, isPublishing: isReviewPublishing } = usePublishWorkflow(
    getPublishReviewOptions(workflow)
  )

  const closeDialog = useCallback(() => {
    setPendingReview(null)
    publishDialog.close()
  }, [publishDialog])

  const workflowDefinition = workflowQuery.data?.version?.workflow_definition
  const version = workflowQuery.data?.version?.version
  const publishedVersionId = workflowQuery.data?.published_version_id ?? workflow?.published_version_id ?? null
  const hasCurrentReview = useWorkflowOutputReview({
    isOpen: publishDialog.isOpen,
    workflow,
    workflowDefinition,
    version,
    publishedVersionId,
    isFetching: workflowQuery.isFetching,
    isLoading: workflowQuery.isLoading,
    error: workflowQuery.error,
    pendingReview,
    setPendingReview,
    reviewOutputContract,
    showError,
  })
  const reviewDialogState = getPublishReviewDialogState({
    isOpen: publishDialog.isOpen,
    isPublishing,
    isReviewPublishing,
    hasCurrentReview,
    workflowId,
    workflowDefinition,
    version,
    isFetching: workflowQuery.isFetching,
    isLoading: workflowQuery.isLoading,
    pendingReview,
  })
  const canPublish = !reviewDialogState.isPublishDisabled
  const publishReviewedVersion = usePublishReviewedVersion(canPublish, pendingReview, onPublishWorkflow)

  return (
    <PublishWorkflowDialog
      isOpen={publishDialog.isOpen}
      isPublishing={reviewDialogState.isPublishing}
      isCheckingContractChanges={reviewDialogState.isCheckingContractChanges}
      isPublishDisabled={reviewDialogState.isPublishDisabled}
      onClose={closeDialog}
      onPublish={publishReviewedVersion}
      breakingChanges={reviewDialogState.breakingChanges}
      contractChanges={reviewDialogState.contractChanges}
      parentWorkflows={reviewDialogState.parentWorkflows}
      onConfirmContractChanges={publishReviewedVersion}
      onCancelBreakingChanges={() => setPendingReview(null)}
    />
  )
}
