import { ActivityTypeEnum } from '@syntara/contracts'
import type { ReactFlowInstance } from '@xyflow/react'
import { useCallback, type Dispatch } from 'react'

import { workflowFetchClient } from '../../../client'
import type { AlertMessage } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { getErrorMessage } from '../../../utils/apiErrors'
import { formatDateTime } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'
import type { BuilderAction } from '../builderReducer'
import { DEFAULT_MAX_WAIT_SECONDS, fetchMaxWaitDuration } from '../node-forms/useMaxWaitDuration'
import { validateWorkflow } from '../utils/validation'
import { validateMinimumWorkflow } from '../utils/validation/rules/validateMinimumWorkflow'
import type { ConflictInfo } from '../VersionConflictDialog'

type ShowAlert = (options: AlertMessage) => void

async function checkVersionConflictBeforeRun(
  workflowId: string,
  loadedVersion: number,
  onRunConflict: (info: ConflictInfo) => void,
  loadedVersionName?: string | null,
  loadedVersionCreatedAt?: string | null
): Promise<boolean> {
  const { data: latest } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
    params: { path: { workflow_id: workflowId } },
  })
  const serverVersion = latest?.current_version ?? latest?.version?.version
  if (serverVersion != null && serverVersion > loadedVersion) {
    onRunConflict({
      currentVersion: serverVersion,
      currentVersionName: latest?.version?.name ?? formatDateTime(latest?.version?.created_at) ?? null,
      expectedVersion: loadedVersion,
      expectedVersionName: loadedVersionName ?? null,
      expectedVersionCreatedAt: loadedVersionCreatedAt ?? null,
      createdByUsername: 'another user',
      createdAt: latest?.updated_at ?? '',
    })
    return true
  }
  return false
}

type ExecuteWorkflowMutate = (
  variables: { body: { workflow_id: string; input_data?: Record<string, unknown>; trigger_node_id: string } },
  options?: {
    onSuccess?: (data: { id?: string }) => void
    onError?: (error: unknown) => void
  }
) => void

type DeleteWorkflowMutate = (
  variables: { params: { path: { workflow_id: string } } },
  options?: {
    onSuccess?: () => void
    onError?: (error: unknown) => void
  }
) => void

export type UseBuilderToolbarHandlersOptions = {
  workflow: { id?: string } | undefined
  workflowName: string
  detailsOpen: boolean
  historyCardOpen: boolean
  reactFlowInstance: ReactFlowInstance
  executionsQuery: { refetch: () => Promise<unknown> }
  dispatch: Dispatch<BuilderAction>
  executeWorkflow: ExecuteWorkflowMutate
  deleteWorkflow: DeleteWorkflowMutate
  showSuccess: ShowAlert
  showError: ShowAlert
  setLocation: (to: string) => void
  handleSaveWorkflow: (options?: { expectedVersionOverride?: number; blockOnWarnings?: boolean }) => Promise<boolean>
  currentWorkflow: WorkflowDefinition | null
  loadedVersion: number | null
  loadedVersionName?: string | null
  loadedVersionCreatedAt?: string | null
  onRunConflict?: (info: ConflictInfo) => void
}

/**
 * Header toolbar actions: details/history toggles, run, delete workflow.
 */
export function useBuilderToolbarHandlers({
  workflow,
  workflowName,
  detailsOpen,
  historyCardOpen,
  reactFlowInstance,
  executionsQuery,
  dispatch,
  executeWorkflow,
  deleteWorkflow,
  showSuccess,
  showError,
  setLocation,
  handleSaveWorkflow,
  currentWorkflow,
  loadedVersion,
  loadedVersionName,
  loadedVersionCreatedAt,
  onRunConflict,
}: UseBuilderToolbarHandlersOptions) {
  const handleRunWorkflow = useCallback(
    async (
      inputData?: Record<string, unknown>,
      triggerNodeId?: string,
      runOptions?: { skipPreflightCheck?: boolean }
    ) => {
      if (!workflow?.id) return

      if (loadedVersion != null && !runOptions?.skipPreflightCheck && onRunConflict) {
        const hasConflict = await checkVersionConflictBeforeRun(
          workflow.id,
          loadedVersion,
          onRunConflict,
          loadedVersionName,
          loadedVersionCreatedAt
        )
        if (hasConflict) {
          dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
          return
        }
      }

      // Always save before running to ensure node positions are persisted.
      // Auto-layout positions don't mark isDirty, so we save unconditionally.
      // blockOnWarnings prevents execution when stale tools were auto-cleared.
      try {
        const saved = await handleSaveWorkflow({ blockOnWarnings: true })
        if (!saved) {
          dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
          return
        }
      } catch {
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      // Validate workflow has minimum requirements to run (after save)
      if (!currentWorkflow) {
        showError({ title: 'Cannot run workflow', description: 'No workflow data available' })
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      const edges = useWorkflowStore.getState().edges
      const activities = currentWorkflow.workflow.activities
      const triggers = currentWorkflow.triggers

      // Check minimum workflow requirements (trigger + node + connection)
      const minimumValidation = validateMinimumWorkflow(activities, edges, triggers)
      if (minimumValidation.length > 0) {
        const errorMessages = minimumValidation.map((error) => error.message).join('\n• ')
        showError({ title: 'Cannot run workflow', description: `${errorMessages}` })
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      // Check all other validation rules (dangling nodes, invalid connections, etc.)
      const validationResult = validateWorkflow(activities, edges, { triggers })
      if (!validationResult.valid) {
        const errorMessages = validationResult.errors.map((error) => error.message).join('\n• ')
        showError({ title: 'Cannot run workflow', description: `Workflow validation failed:\n• ${errorMessages}` })
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      const waitErrors = await validateWaitNodeDurations(activities)
      if (waitErrors.length > 0) {
        showError({ title: 'Cannot run workflow', description: waitErrors.join('\n• ') })
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      executeWorkflow(
        {
          body: {
            workflow_id: workflow.id,
            input_data: inputData ?? {},
            trigger_node_id: triggerNodeId ?? '',
          },
        },
        {
          onSuccess: (data) => {
            dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
            if (data.id) {
              setLocation(`/executions/${data.id}?history=closed`)
            }
          },
          onError: (error) => {
            showError({
              title: 'Failed to run workflow',
              description: `Failed to start workflow "${workflowName}": ${getErrorMessage(error)}`,
            })
            dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
          },
        }
      )
    },
    [
      workflow,
      workflowName,
      executeWorkflow,
      handleSaveWorkflow,
      showError,
      dispatch,
      currentWorkflow,
      setLocation,
      loadedVersion,
      loadedVersionName,
      loadedVersionCreatedAt,
      onRunConflict,
    ]
  )

  const handleDeleteWorkflow = useCallback(() => {
    if (!workflow?.id) return

    deleteWorkflow(
      { params: { path: { workflow_id: workflow.id } } },
      {
        onSuccess: () => {
          showSuccess({ title: 'Workflow deleted', description: `Workflow "${workflowName}" has been deleted.` })
          dispatch({ type: 'SET_DELETE_DIALOG', payload: false })
          setLocation('/workflows')
        },
        onError: (error) => {
          showError({
            title: 'Failed to delete workflow',
            description: `Failed to delete workflow "${workflowName}": ${getErrorMessage(error)}`,
          })
          dispatch({ type: 'SET_DELETE_DIALOG', payload: false })
        },
      }
    )
  }, [workflow, workflowName, deleteWorkflow, showSuccess, showError, setLocation, dispatch])

  const handleToggleDetails = useCallback(() => {
    dispatch({ type: 'TOGGLE_DETAILS' })
    if (!detailsOpen) {
      reactFlowInstance.setNodes((nodes) => nodes.map((node) => ({ ...node, selected: false })))
    }
  }, [reactFlowInstance, detailsOpen, dispatch])

  const handleToggleHistory = useCallback(() => {
    dispatch({ type: 'TOGGLE_HISTORY' })
    if (!historyCardOpen) {
      detachPromise(executionsQuery.refetch())
    }
  }, [historyCardOpen, executionsQuery, dispatch])

  const handleToggleVersionHistory = useCallback(() => {
    dispatch({ type: 'TOGGLE_VERSION_HISTORY' })
  }, [dispatch])

  return {
    handleRunWorkflow,
    handleDeleteWorkflow,
    handleToggleDetails,
    handleToggleHistory,
    handleToggleVersionHistory,
  }
}

async function validateWaitNodeDurations(activities: WorkflowDefinition['workflow']['activities']): Promise<string[]> {
  const waitNodes = activities.filter((a) => a.type === ActivityTypeEnum.WAIT)
  if (waitNodes.length === 0) return []

  const maxWaitSeconds = await fetchMaxWaitDuration().catch(() => DEFAULT_MAX_WAIT_SECONDS)
  const errors: string[] = []

  for (const node of waitNodes) {
    const total = (node.parameters as { duration?: number } | undefined)?.duration ?? 0
    if (total > maxWaitSeconds) {
      errors.push(
        `Wait step "${node.name || 'Untitled'}" duration (${total}s) exceeds maximum allowed (${maxWaitSeconds}s)`
      )
    }
  }

  return errors
}
