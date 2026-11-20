import { useCallback, useEffect, useMemo } from 'react'

import { executionsClient, workflowClient } from '../../client'
import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'

import type { useBuilderSession } from './builderSession'
import { useBuilderConflict } from './hooks/useBuilderConflict'
import { useBuilderSaveWorkflow } from './hooks/useBuilderSaveWorkflow'
import { useBuilderToolbarHandlers } from './hooks/useBuilderToolbarHandlers'
import { useBuilderValidation } from './hooks/useBuilderValidation'
import { useGuardedSaveWorkflow } from './hooks/useGuardedSaveWorkflow'
import { usePublishWorkflow, useUnpublishWorkflow } from './hooks/usePublishWorkflow'
import { useStepEditorAutoSubmitRef } from './hooks/useStepEditorAutoSubmit'
import type { BuilderContentProps } from './types/builderContent'
import { hasTriggerId } from './utils/hasTriggerId'
import { parseImportedDefinition } from './utils/parseImportedDefinition'

export function useBuilderAuthoring(
  { workflow, workflowId, isNew }: BuilderContentProps,
  session: ReturnType<typeof useBuilderSession>
) {
  const {
    dispatch,
    queryClient,
    setLocation,
    builderPermissions,
    stableProjectId,
    isStepEditorOpen,
    reactFlowInstance,
    executionsQuery,
    workflowsListQuery,
    setSaveAttemptedWithoutProject,
    retryWorkflowPermissionContext,
  } = session
  const { registerSaveHandler, unregisterSaveHandler } = session.unsavedChanges
  const { currentWorkflow, markClean } = session.store
  const { workflowName, workflowDescription, stepEditorMode, detailsOpen, historyCardOpen } = session.state
  const { showWarning, showSuccess, showError } = useAlerts()
  const autoSubmitRef = useStepEditorAutoSubmitRef()
  const currentVersion = workflow?.current_version ?? workflow?.version?.version
  const { handleVerifySilent } = useBuilderValidation({
    dispatch,
  })
  const { mutate: createWorkflow, isPending: isCreating } = workflowClient.useMutation('post', '/workflows')
  const { mutate: updateWorkflow, isPending: isUpdating } = workflowClient.useMutation(
    'patch',
    '/workflows/{workflow_id}'
  )
  const { mutate: executeWorkflow } = executionsClient.useMutation('post', '/executions')
  const { mutate: deleteWorkflow, isPending: isDeleting } = workflowClient.useMutation(
    'delete',
    '/workflows/{workflow_id}'
  )
  const { loadedVersion, handleConflict, onVersionUpdated, setActions, conflictDialogProps } = useBuilderConflict({
    workflowId,
    workflowName,
    workflowDescription,
    workflowProjectId: workflow?.project_id,
    selectedProjectId: stableProjectId,
    currentWorkflow,
    currentVersion,
    isNew,
    setLocation,
    showError,
    markClean,
  })

  const { unpublish: unpublishWorkflow } = useUnpublishWorkflow(workflowId)
  const onUnpublish = useCallback(() => {
    if (builderPermissions.canEdit) unpublishWorkflow()
  }, [builderPermissions.canEdit, unpublishWorkflow])
  const saveWorkflow = useBuilderSaveWorkflow({
    currentWorkflow,
    workflowName,
    workflowDescription,
    workflowId,
    isNew,
    selectedProject: stableProjectId ? { id: stableProjectId } : null,
    workflowsListResources: workflowsListQuery.data?.resources,
    queryClient,
    setLocation,
    showSuccess,
    showWarning,
    showError,
    onMissingProjectForCreate: () => setSaveAttemptedWithoutProject(true),
    markClean,
    expectedVersion: loadedVersion,
    onConflict: handleConflict('save'),
    onVersionUpdated,
    onSaveWithValidationIssues: handleVerifySilent,
    onValidationFindings: (errors) => {
      if (errors.length === 0) {
        dispatch({ type: 'CLEAR_VALIDATION_ERRORS' })
        useWorkflowStore.getState().setValidationErrorCount(0)
        return
      }
      dispatch({ type: 'SET_VALIDATION_ERRORS', payload: errors, source: 'save' })
      useWorkflowStore.getState().setValidationErrorCount(errors.length)
    },
    createWorkflow: createWorkflow,
    updateWorkflow,
  })
  const handleSaveWorkflow = useCallback(
    (options?: Parameters<typeof saveWorkflow>[0]) =>
      builderPermissions.canEdit ? saveWorkflow(options) : Promise.resolve(false),
    [builderPermissions.canEdit, saveWorkflow]
  )
  const guardedSaveWorkflow = useGuardedSaveWorkflow({
    handleSaveWorkflow,
    isStepEditorOpen,
    stepEditorMode,
    autoSubmitRef,
    dispatch,
  })

  const { publish: publishWorkflow, isPublishing } = usePublishWorkflow({
    workflowId,
    currentVersion,
    workflowName,
    workflowDescription,
    expectedVersion: loadedVersion,
    onConflict: handleConflict('publish'),
    onVersionUpdated,
  })
  const onPublish = useCallback(
    (...args: Parameters<typeof publishWorkflow>) => {
      if (builderPermissions.canEdit) publishWorkflow(...args)
    },
    [builderPermissions.canEdit, publishWorkflow]
  )

  const { isReadOnly, savedRunState, runWorkflow, runDialogBecameStale } = useBuilderRunSource(workflow, session)
  const {
    handleRunWorkflow,
    handleDeleteWorkflow,
    handleToggleDetails,
    handleToggleHistory,
    handleToggleVersionHistory: baseHandleToggleVersionHistory,
  } = useBuilderToolbarHandlers({
    workflow: workflow,
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
    handleSaveWorkflow: guardedSaveWorkflow,
    currentWorkflow,
    loadedVersion,
    loadedVersionName: workflow?.version?.name ?? null,
    loadedVersionCreatedAt: workflow?.version?.created_at ?? null,
    onRunConflict: handleConflict('run'),
    isReadOnly,
    savedRunState,
    savedVersion: workflow?.version?.version ?? currentVersion,
    refreshSavedWorkflow: retryWorkflowPermissionContext,
    canRun: builderPermissions.canRun,
    canDelete: builderPermissions.canDelete,
  })
  useEffect(() => {
    registerSaveHandler(handleSaveWorkflow)
    setActions({ handleSaveWorkflow, onPublish, handleRunWorkflow })
    return () => unregisterSaveHandler()
  }, [handleSaveWorkflow, onPublish, handleRunWorkflow, registerSaveHandler, unregisterSaveHandler, setActions])

  return {
    autoSubmitRef,
    createWorkflow,
    isCreating,
    isUpdating,
    isDeleting,
    isPublishing,
    onPublish,
    onUnpublish,
    guardedSaveWorkflow,
    handleSaveWorkflow,
    onVersionUpdated,
    conflictDialogProps,
    handleRunWorkflow,
    handleDeleteWorkflow,
    handleToggleDetails,
    handleToggleHistory,
    baseHandleToggleVersionHistory,
    isReadOnly,
    savedRunState,
    runWorkflow,
    runDialogBecameStale,
  }
}

function useBuilderRunSource(
  workflow: BuilderContentProps['workflow'],
  { builderPermissions, dispatch, state, store }: ReturnType<typeof useBuilderSession>
) {
  const isReadOnly = !builderPermissions.canEdit
  const savedWorkflowDefinition = workflow?.version?.workflow_definition
  // Only the read-only run path consumes the parsed saved definition, so skip the
  // full nested-to-flat transform for sessions that can edit.
  const savedRunState = useMemo(
    () => (isReadOnly && savedWorkflowDefinition ? parseImportedDefinition(savedWorkflowDefinition) : undefined),
    [isReadOnly, savedWorkflowDefinition]
  )
  const runWorkflow = isReadOnly ? savedRunState?.workflowDef : store.currentWorkflow
  const runDialogBecameStale =
    state.confirmDialogOpen &&
    (state.runSelection?.readOnly !== isReadOnly ||
      !builderPermissions.canRun ||
      !hasTriggerId(runWorkflow?.triggers, state.runSelection?.triggerId))
  // React's documented pattern for adjusting derived state during render: the
  // re-render this triggers discards the stale-dialog paint, and consumers
  // additionally mask the dialog with runDialogBecameStale.
  if (runDialogBecameStale) dispatch({ type: 'SET_CONFIRM_DIALOG', payload: false })
  return { isReadOnly, savedRunState, runWorkflow, runDialogBecameStale }
}
