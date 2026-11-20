import { AlertActionLink } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { workflowClient } from '../../client'
import { invalidateWorkflowQueries } from '../../hooks/invalidateWorkflowQueries'
import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'

import type { BuilderContentProps } from './types/builderContent'
import { buildWorkflowDefinition, transformStepParameters } from './utils/workflowDefinitionBuilder'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

export function useBuilderDuplication({
  workflow,
  workflowName,
  workflowDescription,
  currentWorkflow,
  canCreate,
  guardedSaveWorkflow,
  setLocation,
}: Pick<BuilderContentProps, 'workflow'> & {
  workflowName: string
  workflowDescription: string
  currentWorkflow: WorkflowDefinition | null
  canCreate: boolean
  guardedSaveWorkflow: () => Promise<boolean>
  setLocation: (to: string) => void
}) {
  const queryClient = useQueryClient()
  const { showAlert, showError } = useAlerts()
  const [pendingDuplicateNavigation, setPendingDuplicateNavigation] = useState<string | null>(null)
  const { mutate: duplicateWorkflow, isPending: isDuplicating } = workflowClient.useMutation('post', '/workflows')

  const executeDuplicateWorkflow = useCallback(
    (definition: Record<string, unknown>) => {
      if (!canCreate || isDuplicating || !workflow?.name || !workflow.project_id) return
      const timestamp = Date.now().toString(36)
      const suffix = ` - duplicate-${timestamp}`
      const maxBaseLength = 255 - suffix.length
      const baseName = workflow.name.length > maxBaseLength ? workflow.name.slice(0, maxBaseLength) : workflow.name
      const duplicateName = `${baseName}${suffix}`

      const nodes = Array.isArray(definition.nodes) ? (definition.nodes as Array<Record<string, unknown>>) : undefined
      const transformedDefinition = {
        ...definition,
        nodes: nodes?.map((node) => {
          const parameters = node.parameters as Record<string, unknown> | undefined
          if (parameters && typeof node.type === 'string') {
            return { ...node, parameters: transformStepParameters(node.type, parameters) }
          }
          return node
        }),
      }

      duplicateWorkflow(
        {
          body: {
            name: duplicateName,
            description: workflowDescription,
            workflow_definition: transformedDefinition,
            labels: workflow.labels ?? {},
            project_id: workflow.project_id,
          },
        },
        {
          onSuccess: (created) => {
            showAlert({
              variant: 'success',
              autoDismiss: true,
              title: 'Workflow duplicated',
              description: `Created "${duplicateName}"`,
              actionLinks: created?.id ? (
                <AlertActionLink
                  onClick={() => {
                    // Check isDirty at click time to detect unsaved changes.
                    // Note: If user makes edits between click and dialog render (~100ms),
                    // those edits won't trigger the dialog. This is acceptable - the timing
                    // window is too small to be a practical concern.
                    if (useWorkflowStore.getState().isDirty) {
                      setPendingDuplicateNavigation(`/workflow-builder/${created.id}`)
                    } else {
                      setLocation(`/workflow-builder/${created.id}`)
                    }
                  }}
                >
                  Open workflow
                </AlertActionLink>
              ) : undefined,
            })
            detachPromise(invalidateWorkflowQueries(queryClient))
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to duplicate workflow', description: getErrorMessage(error) })
          },
        }
      )
    },
    [
      canCreate,
      isDuplicating,
      workflow,
      duplicateWorkflow,
      queryClient,
      showAlert,
      showError,
      setLocation,
      workflowDescription,
    ]
  )

  const handleDuplicateVersion = useCallback(
    (version: WorkflowVersion) => {
      const definition = version.workflow_definition
      if (!definition) {
        showError({ title: 'Failed to duplicate workflow', description: 'Version has no definition to duplicate' })
        return
      }
      executeDuplicateWorkflow(definition)
    },
    [executeDuplicateWorkflow, showError]
  )

  const handleDuplicateWorkflow = useCallback(() => {
    if (!currentWorkflow) {
      showError({ title: 'Cannot duplicate workflow', description: 'Save the workflow before duplicating.' })
      return
    }
    const { edges, nodePositions } = useWorkflowStore.getState()
    const activities = currentWorkflow.workflow.activities ?? []
    const triggers = currentWorkflow.triggers ?? []
    const definition = buildWorkflowDefinition({
      workflowName: workflowName,
      workflowDescription: workflowDescription,
      activities: activities,
      triggers: triggers,
      edges,
      nodePositions,
    })
    executeDuplicateWorkflow(definition)
  }, [currentWorkflow, workflowName, workflowDescription, executeDuplicateWorkflow, showError])

  const handleSaveBeforeDuplicateNavigation = useCallback(async (): Promise<boolean> => {
    const destinationPath = pendingDuplicateNavigation
    const saved = await guardedSaveWorkflow()
    if (saved) {
      setPendingDuplicateNavigation(null)
      if (destinationPath) {
        setLocation(destinationPath)
      }
    }
    return saved
  }, [pendingDuplicateNavigation, guardedSaveWorkflow, setLocation])

  const handleNavigateWithoutSaving = useCallback(() => {
    if (pendingDuplicateNavigation) {
      setLocation(pendingDuplicateNavigation)
    }
    setPendingDuplicateNavigation(null)
  }, [pendingDuplicateNavigation, setLocation])

  const handleCancelDuplicateNavigation = useCallback(() => {
    setPendingDuplicateNavigation(null)
  }, [])

  return {
    handleDuplicateWorkflow,
    onDuplicateVersion: (version: WorkflowVersion) => detachPromise(handleDuplicateVersion(version)),
    navigationDialog: {
      isOpen: pendingDuplicateNavigation !== null,
      onSave: handleSaveBeforeDuplicateNavigation,
      onViewWithoutSaving: handleNavigateWithoutSaving,
      onCancel: handleCancelDuplicateNavigation,
    },
  }
}
