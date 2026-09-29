import { useCallback } from 'react'

import { workflowClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'

type UseForkWorkflowOptions = {
  workflowDefinition: Record<string, unknown> | undefined | null
  workflowName: string
  projectId?: string | null
}

export function useForkWorkflow({ workflowDefinition, workflowName, projectId }: UseForkWorkflowOptions) {
  const { showError } = useAlerts()
  const { mutateAsync, isPending: isForkLoading } = workflowClient.useMutation('post', '/workflows')

  const forkAsNewWorkflow = useCallback(async (): Promise<string | undefined> => {
    if (!workflowDefinition) return undefined
    if (!projectId) {
      showError({ title: 'Fork failed', description: 'Project ID is required to create a workflow' })
      return undefined
    }
    try {
      const timestamp = Date.now().toString(36)
      const forkName = `${workflowName} - copy-${timestamp}`

      const result = await mutateAsync({
        body: {
          name: forkName,
          description: '',
          workflow_definition: workflowDefinition,
          project_id: projectId,
        },
      })

      return result?.id
    } catch (err: unknown) {
      showError({ title: 'Fork failed', description: getErrorMessage(err) })
      return undefined
    }
  }, [workflowDefinition, workflowName, projectId, mutateAsync, showError])

  return { forkAsNewWorkflow, isForkLoading }
}
