import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { workflowClient } from '../../../client'

type TriggerBreakingChanges = WorkflowAPI.components['schemas']['TriggerBreakingChanges']
type WorkflowReference = WorkflowAPI.components['schemas']['WorkflowReferenceRead']
type BreakingChangesResponse = WorkflowAPI.components['schemas']['BreakingChangesResponse']

type ContractReviewErrorHandler = (error: unknown) => void

export function useOutputContractReview(workflowId: string | null) {
  const [breakingChanges, setBreakingChanges] = useState<TriggerBreakingChanges[]>([])
  const [contractChanges, setContractChanges] = useState<TriggerBreakingChanges[]>([])
  const [parentWorkflows, setParentWorkflows] = useState<WorkflowReference[]>([])
  const { mutate, isPending: isChecking } = workflowClient.useMutation(
    'post',
    '/workflows/{workflow_id}/check_subworkflow_output_contract_changes'
  )

  const clearReview = useCallback(() => {
    setBreakingChanges([])
    setContractChanges([])
    setParentWorkflows([])
  }, [])

  const reviewOutputContract = useCallback(
    (
      workflowDefinition: Record<string, unknown>,
      onError: ContractReviewErrorHandler
    ): Promise<BreakingChangesResponse | null> => {
      if (!workflowId) return Promise.resolve(null)

      return new Promise((resolve) => {
        mutate(
          {
            params: { path: { workflow_id: workflowId } },
            body: { workflow_definition: workflowDefinition },
          },
          {
            onSuccess: (response) => {
              setBreakingChanges(response.triggers)
              setContractChanges(response.contract_changes ?? [])
              setParentWorkflows(response.parent_workflows ?? [])
              resolve(response)
            },
            onError: (error: unknown) => {
              onError(error)
              resolve(null)
            },
          }
        )
      })
    },
    [mutate, workflowId]
  )

  return {
    breakingChanges,
    contractChanges,
    parentWorkflows,
    isChecking,
    clearReview,
    reviewOutputContract,
  }
}
