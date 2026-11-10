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
import { DEFAULT_MAX_WAIT_SECONDS, fetchMaxWaitDuration } from '../step-forms/useMaxWaitDuration'
import type { EdgeConnection } from '../types/edge'
import { parseImportedDefinition } from '../utils/parseImportedDefinition'
import { validateWorkflow } from '../utils/validation'
import { validateMinimumWorkflow } from '../utils/validation/rules/validateMinimumWorkflow'
import type { ConflictInfo } from '../VersionConflictDialog'

type ShowAlert = (options: AlertMessage) => void

type CheckVersionConflictBeforeRunOptions = {
  workflowId: string
  loadedVersion: number
  onRunConflict: (info: ConflictInfo) => void
  loadedVersionName?: string | null
  loadedVersionCreatedAt?: string | null
}

async function checkVersionConflictBeforeRun({
  workflowId,
  loadedVersion,
  onRunConflict,
  loadedVersionName,
  loadedVersionCreatedAt,
}: CheckVersionConflictBeforeRunOptions): Promise<boolean> {
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

async function stopForVersionConflict(options: {
  workflowId: string
  loadedVersion: number | null
  skipPreflightCheck: boolean
  onRunConflict?: (info: ConflictInfo) => void
  loadedVersionName?: string | null
  loadedVersionCreatedAt?: string | null
  dispatch: Dispatch<BuilderAction>
}): Promise<boolean> {
  if (options.loadedVersion === null || options.skipPreflightCheck || !options.onRunConflict) return false
  const hasConflict = await checkVersionConflictBeforeRun({
    workflowId: options.workflowId,
    loadedVersion: options.loadedVersion,
    onRunConflict: options.onRunConflict,
    loadedVersionName: options.loadedVersionName,
    loadedVersionCreatedAt: options.loadedVersionCreatedAt,
  })
  if (hasConflict) options.dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
  return hasConflict
}

async function saveBeforeWorkflowRun(
  isReadOnly: boolean,
  handleSaveWorkflow: UseBuilderToolbarHandlersOptions['handleSaveWorkflow'],
  dispatch: Dispatch<BuilderAction>
): Promise<boolean> {
  if (isReadOnly) return true
  try {
    const saved = await handleSaveWorkflow({ blockOnWarnings: true })
    if (!saved) dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
    return saved
  } catch {
    dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
    return false
  }
}

type WorkflowRunState = {
  workflow: WorkflowDefinition
  edges: EdgeConnection[]
}

function getWorkflowRunState(
  isReadOnly: boolean,
  savedWorkflowDefinition: Record<string, unknown> | undefined,
  currentWorkflow: WorkflowDefinition | null
): WorkflowRunState | null {
  if (isReadOnly) {
    if (!savedWorkflowDefinition) return null
    const saved = parseImportedDefinition(savedWorkflowDefinition)
    return { workflow: saved.workflowDef, edges: saved.edges }
  }
  if (!currentWorkflow) return null
  return { workflow: currentWorkflow, edges: useWorkflowStore.getState().edges }
}

async function getWorkflowRunValidationError({ workflow, edges }: WorkflowRunState): Promise<string | null> {
  const activities = workflow.workflow.activities
  const triggers = workflow.triggers
  const minimumValidation = validateMinimumWorkflow(activities, edges, triggers)
  if (minimumValidation.length > 0) {
    return minimumValidation.map((error) => error.message).join('\n• ')
  }
  const validationResult = validateWorkflow(activities, edges, { triggers })
  if (!validationResult.valid) {
    return `Workflow validation failed:\n• ${validationResult.errors.map((error) => error.message).join('\n• ')}`
  }
  const waitErrors = await validateWaitNodeDurations(activities)
  return waitErrors.length > 0 ? waitErrors.join('\n• ') : null
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
  isReadOnly?: boolean
  savedWorkflowDefinition?: Record<string, unknown>
  canDelete?: boolean
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
  isReadOnly = false,
  savedWorkflowDefinition,
  canDelete = true,
}: UseBuilderToolbarHandlersOptions) {
  const handleRunWorkflow = useCallback(
    async (
      inputData?: Record<string, unknown>,
      triggerNodeId?: string,
      runOptions?: { skipPreflightCheck?: boolean }
    ) => {
      if (!workflow?.id) return

      if (
        await stopForVersionConflict({
          workflowId: workflow.id,
          loadedVersion,
          skipPreflightCheck: runOptions?.skipPreflightCheck === true,
          onRunConflict,
          loadedVersionName,
          loadedVersionCreatedAt,
          dispatch,
        })
      )
        return

      // Auto-layout positions do not mark dirty, so editable runs always save.
      if (!(await saveBeforeWorkflowRun(isReadOnly, handleSaveWorkflow, dispatch))) return

      const runState = getWorkflowRunState(isReadOnly, savedWorkflowDefinition, currentWorkflow)
      if (!runState) {
        showError({
          title: 'Cannot run workflow',
          description: isReadOnly ? 'No saved workflow definition is available' : 'No workflow data available',
        })
        dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
        return
      }

      const validationError = await getWorkflowRunValidationError(runState)
      if (validationError) {
        showError({ title: 'Cannot run workflow', description: validationError })
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
      isReadOnly,
      savedWorkflowDefinition,
    ]
  )

  const handleDeleteWorkflow = useCallback(() => {
    if (!canDelete || !workflow?.id) return

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
  }, [canDelete, workflow, workflowName, deleteWorkflow, showSuccess, showError, setLocation, dispatch])

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
