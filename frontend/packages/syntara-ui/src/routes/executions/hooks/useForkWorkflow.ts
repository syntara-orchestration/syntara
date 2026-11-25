import { useCallback, useState } from 'react'

import { workflowClient } from '../../../client'
import { useNodeKindsQuery } from '../../../hooks/useNodeKindsQuery'
import { useAlerts } from '../../../providers/alerts/AlertContext'
import { getErrorMessage } from '../../../utils/apiErrors'
import { extractNodeKindDenials, isNodeKindWriteDeniedError } from '../../../utils/nodeKindDenials'
import {
  STEP_TYPE_PERMISSIONS_LOADING_MESSAGE,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
} from '../../builder/stepTypePaletteGating'
import {
  blockedForkStepTypes,
  forkLosesAllTriggers,
  withoutForkStepTypes,
  type BlockedFork,
  type RawWorkflowDefinition,
} from '../forkStepTypes'

type UseForkWorkflowOptions = {
  workflowDefinition: Record<string, unknown> | undefined | null
  workflowName: string
  projectId?: string | null
}

/** Alert title when the fork is refused because of step-type write permissions. */
export const FORK_DENIED_TITLE = 'Cannot fork workflow'

type PendingFork = BlockedFork & { kinds: string[] }

function forkErrorAlert(err: unknown): { title: string; description: string } {
  if (!isNodeKindWriteDeniedError(err)) return { title: 'Fork failed', description: getErrorMessage(err) }
  const labels = extractNodeKindDenials(err).map(({ label }) => label)
  return {
    title: FORK_DENIED_TITLE,
    description: labels.length
      ? `You don't have permission to write these step types: ${labels.join(', ')}.`
      : getErrorMessage(err),
  }
}

/**
 * Fork a run's definition as a new workflow in its project.
 *
 * Checks the definition against the project's step-type verdicts first (UX
 * only; the server enforces). When some step types are denied, the fork waits
 * in `blockedFork` until the user confirms leaving those steps out
 * (`confirmBlockedFork`) or cancels (`cancelBlockedFork`). Fails closed while
 * the verdicts are loading or unavailable.
 */
export function useForkWorkflow({ workflowDefinition, workflowName, projectId }: UseForkWorkflowOptions) {
  const { showError } = useAlerts()
  const { mutateAsync, isPending: isForkLoading } = workflowClient.useMutation('post', '/workflows')
  const { nodeKindByKind, isLoading, isUnavailable } = useNodeKindsQuery(projectId, {
    enabled: Boolean(workflowDefinition),
  })
  const [pendingFork, setPendingFork] = useState<PendingFork | null>(null)

  const createFork = useCallback(
    async (definition: RawWorkflowDefinition, project: string): Promise<string | undefined> => {
      try {
        const timestamp = Date.now().toString(36)
        const forkName = `${workflowName} - copy-${timestamp}`

        const result = await mutateAsync({
          body: {
            name: forkName,
            description: '',
            workflow_definition: definition,
            project_id: project,
          },
        })

        return result?.id
      } catch (err: unknown) {
        showError(forkErrorAlert(err))
        return undefined
      }
    },
    [workflowName, mutateAsync, showError]
  )

  const forkAsNewWorkflow = useCallback(async (): Promise<string | undefined> => {
    if (!workflowDefinition) return undefined
    if (!projectId) {
      showError({ title: 'Fork failed', description: 'Project ID is required to create a workflow' })
      return undefined
    }
    if (isLoading || isUnavailable) {
      const description = isLoading ? STEP_TYPE_PERMISSIONS_LOADING_MESSAGE : STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
      showError({ title: FORK_DENIED_TITLE, description })
      return undefined
    }
    const blocked = blockedForkStepTypes(workflowDefinition, nodeKindByKind)
    if (blocked.length > 0) {
      const kinds = blocked.map(({ kind }) => kind)
      setPendingFork({
        kinds,
        labels: blocked.map(({ label }) => label),
        losesAllTriggers: forkLosesAllTriggers(workflowDefinition, kinds),
      })
      return undefined
    }
    return createFork(workflowDefinition, projectId)
  }, [workflowDefinition, projectId, isLoading, isUnavailable, nodeKindByKind, createFork, showError])

  /** Creates the fork without the blocked step types; resolves to the new workflow id, if any. */
  const confirmBlockedFork = useCallback(async (): Promise<string | undefined> => {
    if (!pendingFork || !workflowDefinition || !projectId || isForkLoading) return undefined
    const id = await createFork(withoutForkStepTypes(workflowDefinition, pendingFork.kinds), projectId)
    setPendingFork(null)
    return id
  }, [pendingFork, workflowDefinition, projectId, isForkLoading, createFork])

  const cancelBlockedFork = useCallback(() => setPendingFork(null), [])

  const blockedFork: BlockedFork | null = pendingFork

  return { forkAsNewWorkflow, isForkLoading, blockedFork, confirmBlockedFork, cancelBlockedFork }
}
