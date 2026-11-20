import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { workflowClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts'
import type { AlertMessage } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'

import { useOutputContractReview } from './useOutputContractReview'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

type PendingVersionPublish = {
  version: number
  publishName?: string
  changeDescription?: string
  workflowDefinition: Record<string, unknown>
  review?: WorkflowAPI.components['schemas']['BreakingChangesResponse']
  onSettled?: () => void
}

type UseVersionHistoryPublishingParams = Readonly<{
  workflowId: string | null
  versions: WorkflowVersion[] | undefined
  refetchVersions: () => Promise<unknown>
  onVersionUpdated?: (version: number) => void
}>

function showMissingVersionDefinition(showError: (options: AlertMessage) => void): void {
  showError({
    title: 'Failed to check output contract changes',
    description: 'Version definition is unavailable',
  })
}

export function useVersionHistoryPublishing({
  workflowId,
  versions,
  refetchVersions,
  onVersionUpdated,
}: UseVersionHistoryPublishingParams) {
  const queryClient = useQueryClient()
  const { showSuccess, showError } = useAlerts()
  const {
    breakingChanges,
    contractChanges,
    parentWorkflows,
    isChecking: isCheckingOutputContract,
    clearReview: clearOutputContractReview,
    reviewOutputContract: runOutputContractReview,
  } = useOutputContractReview(workflowId)
  const [pendingPublish, setPendingPublish] = useState<PendingVersionPublish | null>(null)
  const publishMutation = workflowClient.useMutation('post', '/workflows/{workflow_id}/versions/{version}/publish')

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
            if (data?.current_version != null) onVersionUpdated?.(data.current_version)
            detachPromise(refetchVersions())
            detachPromise(
              queryClient.invalidateQueries({
                predicate: (query) =>
                  query.queryKey[0] === 'get' &&
                  typeof query.queryKey[1] === 'string' &&
                  query.queryKey[1].startsWith('/workflows'),
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
    [workflowId, publishMutation, showSuccess, showError, onVersionUpdated, refetchVersions, queryClient]
  )

  const reviewVersionForPublish = useCallback(
    (version: number) => {
      clearOutputContractReview()
      if (!workflowId) return

      const workflowDefinition = versions?.find((item) => item.version === version)?.workflow_definition
      if (!workflowDefinition) {
        setPendingPublish(null)
        showMissingVersionDefinition(showError)
        return
      }

      const pending: PendingVersionPublish = { version, workflowDefinition }
      setPendingPublish(pending)
      detachPromise(
        runOutputContractReview(workflowDefinition, (error) => {
          setPendingPublish((current) => (current?.version === version ? null : current))
          showError({ title: 'Failed to check output contract changes', description: getErrorMessage(error) })
        }).then((review) => {
          if (!review) return
          setPendingPublish((current) =>
            current?.version === version && current.workflowDefinition === workflowDefinition
              ? { ...current, review }
              : current
          )
        })
      )
    },
    [workflowId, versions, clearOutputContractReview, runOutputContractReview, showError]
  )

  const publishVersion = useCallback(
    (version: number, publishName?: string, changeDescription?: string, onSettled?: () => void) => {
      if (!workflowId) return
      if (pendingPublish?.version === version) {
        if (!pendingPublish.review) return
        const reviewedPending = { ...pendingPublish, publishName, changeDescription, onSettled }
        if (pendingPublish.review.has_breaking_changes || pendingPublish.review.has_contract_changes) {
          setPendingPublish(reviewedPending)
          return
        }
        setPendingPublish(null)
        publishVersionNow(reviewedPending)
        return
      }

      const workflowDefinition = versions?.find((item) => item.version === version)?.workflow_definition
      if (!workflowDefinition) {
        showMissingVersionDefinition(showError)
        return
      }
      const pending: PendingVersionPublish = {
        version,
        publishName,
        changeDescription,
        workflowDefinition,
        onSettled,
      }
      clearOutputContractReview()
      setPendingPublish(pending)
      detachPromise(
        runOutputContractReview(workflowDefinition, (error) => {
          setPendingPublish(null)
          showError({ title: 'Failed to check output contract changes', description: getErrorMessage(error) })
        }).then((review) => {
          if (!review) return
          const reviewedPending = { ...pending, review }
          if (review.has_breaking_changes || review.has_contract_changes) {
            setPendingPublish(reviewedPending)
            return
          }
          setPendingPublish(null)
          publishVersionNow(reviewedPending)
        })
      )
    },
    [
      workflowId,
      versions,
      pendingPublish,
      clearOutputContractReview,
      runOutputContractReview,
      publishVersionNow,
      showError,
    ]
  )

  const confirmPublishVersion = useCallback(
    (publishName?: string, changeDescription?: string, onSettled?: () => void) => {
      if (!pendingPublish?.review) return
      const pending = {
        ...pendingPublish,
        publishName: publishName ?? pendingPublish.publishName,
        changeDescription: changeDescription ?? pendingPublish.changeDescription,
        onSettled: onSettled ?? pendingPublish.onSettled,
      }
      clearOutputContractReview()
      setPendingPublish(null)
      publishVersionNow(pending)
    },
    [pendingPublish, clearOutputContractReview, publishVersionNow]
  )

  const cancelBreakingChangeWarning = useCallback(() => {
    clearOutputContractReview()
    setPendingPublish(null)
  }, [clearOutputContractReview])

  return {
    publishVersion,
    reviewVersionForPublish,
    isPublishingVersion: publishMutation.isPending || isCheckingOutputContract,
    isCheckingOutputContract,
    reviewedPublishVersion: pendingPublish?.review ? pendingPublish.version : null,
    breakingChanges,
    contractChanges,
    parentWorkflows,
    confirmPublishVersion,
    cancelBreakingChangeWarning,
  }
}
