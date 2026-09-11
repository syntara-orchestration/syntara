import { useCallback, useRef, useState } from 'react'

import { executionsFetchClient, workflowFetchClient } from '../../../client'
import { useDialogState } from '../../../hooks/useDialogState'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { buildWorkflowDefinition } from '../utils/workflowDefinitionBuilder'
import type { ConflictAction, ConflictInfo } from '../VersionConflictDialog'

type ConflictDialogData = { action: ConflictAction; info: ConflictInfo }

type UseBuilderConflictParams = {
  workflowId: string | null
  workflowName: string
  workflowDescription: string
  workflowProjectId: string | undefined
  selectedProjectId: string | undefined
  currentWorkflow: WorkflowDefinition | null
  currentVersion: number | undefined
  isNew: boolean
  setLocation: (to: string) => void
  showError: (options: { title: string; description: string }) => void
  markClean: () => void
}

export type ConflictActions = {
  handleSaveWorkflow: (options?: { expectedVersionOverride?: number }) => Promise<boolean>
  onPublish: (
    publishName?: string,
    description?: string,
    onSettled?: () => void,
    callOptions?: { expectedVersionOverride?: number; versionOverride?: number }
  ) => void
  handleRunWorkflow: (
    inputData?: Record<string, unknown>,
    triggerNodeId?: string,
    runOptions?: { skipPreflightCheck?: boolean }
  ) => Promise<void>
}

/** Manages version conflict detection and resolution for the workflow builder. Tracks the loaded version, opens a conflict dialog when a stale save/publish/run is detected, and provides handlers for the three resolution paths: save as newest, duplicate, or refresh. */
export function useBuilderConflict(params: UseBuilderConflictParams) {
  const {
    workflowId,
    workflowName,
    workflowDescription,
    workflowProjectId,
    selectedProjectId,
    currentWorkflow,
    currentVersion,
    isNew,
    setLocation,
    showError,
    markClean,
  } = params

  const conflictDialog = useDialogState<ConflictDialogData>()
  const [isConflictLoading, setIsConflictLoading] = useState(false)
  const lastSavedVersionRef = useRef<number | null>(null)
  const actionsRef = useRef<ConflictActions | null>(null)
  const setActions = useCallback((actions: ConflictActions) => {
    actionsRef.current = actions
  }, [])

  const [loadedVersion, setLoadedVersion] = useState<number | null>(null)
  if (loadedVersion === null && currentVersion != null && !isNew) {
    setLoadedVersion(currentVersion)
  }

  const conflictDialogOpen = conflictDialog.open
  const handleConflict = useCallback(
    (action: ConflictAction) => (info: ConflictInfo) => {
      conflictDialogOpen({ action, info })
    },
    [conflictDialogOpen]
  )

  const onVersionUpdated = useCallback((v: number) => {
    setLoadedVersion(v)
    lastSavedVersionRef.current = v
  }, [])

  /** Re-submits the user's changes against the latest version, then optionally continues with publish or run. */
  const handleSaveAsNewest = useCallback(
    async (action: ConflictAction) => {
      const actions = actionsRef.current
      if (!actions) return
      const conflictVersion = conflictDialog.item?.info.currentVersion
      setIsConflictLoading(true)
      try {
        const saved = await actions.handleSaveWorkflow(
          conflictVersion != null ? { expectedVersionOverride: conflictVersion } : undefined
        )
        if (!saved) {
          conflictDialog.close()
          setIsConflictLoading(false)
          return
        }
        if (action === 'publish') {
          actions.onPublish(
            undefined,
            undefined,
            () => {
              conflictDialog.close()
              setIsConflictLoading(false)
            },
            {
              expectedVersionOverride: lastSavedVersionRef.current ?? undefined,
              versionOverride: lastSavedVersionRef.current ?? undefined,
            }
          )
          return
        }
        if (action === 'run') {
          conflictDialog.close()
          await actions.handleRunWorkflow(undefined, undefined, { skipPreflightCheck: true })
          setIsConflictLoading(false)
          return
        }
        conflictDialog.close()
        setIsConflictLoading(false)
      } catch {
        conflictDialog.close()
        setIsConflictLoading(false)
      }
    },
    [conflictDialog]
  )

  /** Creates a copy of the current workflow with the user's unsaved changes, then optionally publishes or runs it. */
  const handleDuplicateWorkflow = useCallback(
    async (action: ConflictAction) => {
      if (!workflowId || !currentWorkflow) return
      setIsConflictLoading(true)
      try {
        const { edges, nodePositions } = useWorkflowStore.getState()
        const definition = buildWorkflowDefinition(
          workflowName,
          workflowDescription,
          currentWorkflow.workflow.activities ?? [],
          currentWorkflow.triggers ?? [],
          { edges, nodePositions }
        )
        const projectId = workflowProjectId ?? selectedProjectId

        const { data: created, error: createError } = await workflowFetchClient.POST('/workflows', {
          body: {
            name: `${workflowName} (Copy)`,
            description: workflowDescription,
            workflow_definition: definition as Parameters<
              typeof workflowFetchClient.POST
            >[1]['body']['workflow_definition'],
            project_id: projectId ?? '',
          },
        })
        if (createError || !created?.id) {
          showError({ title: 'Duplicate failed', description: 'Failed to create duplicate workflow' })
          return
        }
        if (action === 'run') {
          const firstTrigger = currentWorkflow.triggers?.[0] as { id?: string } | undefined
          const { data: runData, error: runError } = await executionsFetchClient.POST('/executions', {
            body: {
              workflow_id: created.id,
              input_data: {},
              trigger_node_id: firstTrigger?.id ?? '',
            },
          })
          conflictDialog.close()
          if (runError || !runData?.id) {
            showError({ title: 'Run failed', description: 'Workflow duplicated but failed to run' })
            setLocation(`/workflow-builder/${created.id}`)
          } else {
            setLocation(`/executions/${runData.id}?history=closed`)
          }
          return
        }
        if (action === 'publish') {
          const createdVersion = created.current_version ?? 1
          await workflowFetchClient.POST('/workflows/{workflow_id}/versions/{version}/publish', {
            params: { path: { workflow_id: created.id, version: createdVersion } },
            body: { name: null, change_description: null },
          })
        }
        conflictDialog.close()
        setLocation(`/workflow-builder/${created.id}`)
      } finally {
        setIsConflictLoading(false)
      }
    },
    [
      workflowId,
      currentWorkflow,
      workflowName,
      workflowDescription,
      workflowProjectId,
      selectedProjectId,
      conflictDialog,
      setLocation,
      showError,
    ]
  )

  /** Discards the user's changes and reloads the page to pick up the latest version. */
  const handleRefreshToLatest = useCallback(() => {
    conflictDialog.close()
    markClean()
    window.location.reload()
  }, [conflictDialog, markClean])

  return {
    loadedVersion,
    handleConflict,
    onVersionUpdated,
    setActions,
    conflictDialogProps: {
      isOpen: conflictDialog.isOpen,
      onClose: conflictDialog.close,
      conflictAction: conflictDialog.item?.action ?? 'save',
      conflictInfo: conflictDialog.item?.info,
      onSaveAsNewest: handleSaveAsNewest,
      onDuplicate: handleDuplicateWorkflow,
      onRefreshToLatest: handleRefreshToLatest,
      isLoading: isConflictLoading,
    },
  }
}
