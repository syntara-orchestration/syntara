import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback } from 'react'

import type { AlertConfig, AlertMessage } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import type { BuilderAction } from '../builderReducer'
import { applyImportToCanvas, type PendingImportData } from '../useWorkflowImportExport'
import { buildWorkflowDefinition } from '../utils/workflowDefinitionBuilder'

import type { UseBuilderSaveWorkflowParams } from './useBuilderSaveWorkflow'

type CreateWorkflowBody = WorkflowAPI.paths['/workflows']['post']['requestBody']['content']['application/json']

export type UseBuilderImportHandlersParams = {
  dispatch: (action: BuilderAction) => void
  markDirty: () => void
  selectedProject: { id: string } | null
  createWorkflow: UseBuilderSaveWorkflowParams['createWorkflow']
  setLocation: (to: string) => void
  showAlert: (config: AlertConfig) => void
  showSuccess: (options: AlertMessage) => void
  showError: (options: AlertMessage) => void
  showInfo: (options: AlertMessage) => void
}

export function useBuilderImportHandlers(
  params: UseBuilderImportHandlersParams,
  pendingImport: PendingImportData | null,
  setPendingImport: (data: PendingImportData | null) => void
) {
  const {
    dispatch,
    markDirty,
    selectedProject,
    createWorkflow,
    setLocation,
    showAlert,
    showSuccess,
    showError,
    showInfo,
  } = params

  const handleImportCurrent = useCallback(() => {
    if (!pendingImport) return
    applyImportToCanvas(pendingImport, dispatch, markDirty, showInfo)
    setPendingImport(null)
  }, [pendingImport, dispatch, markDirty, showInfo, setPendingImport])

  const handleImportNew = useCallback(() => {
    if (!pendingImport) return
    const projectId = selectedProject?.id
    if (!projectId) {
      showError({ title: 'Project required', description: 'Select a project to import this workflow.' })
      return
    }
    const importName = pendingImport.name || 'imported-workflow'
    const importDescription = pendingImport.description || importName
    const activities = pendingImport.workflowDef.workflow.activities ?? []
    const triggers = pendingImport.workflowDef.triggers ?? []
    const fullDefinition = buildWorkflowDefinition(importName, importDescription, activities, triggers, {
      edges: pendingImport.edges,
      nodePositions: pendingImport.nodePositions,
    })
    createWorkflow(
      {
        body: {
          name: importName,
          description: importDescription,
          workflow_definition: fullDefinition as unknown as CreateWorkflowBody['workflow_definition'],
          project_id: projectId,
          is_import: true,
        },
      },
      {
        onSuccess: (data) => {
          setPendingImport(null)
          const { validation_result: validationResult } = data
          if (validationResult?.warning_count) {
            const warnings = (validationResult.findings ?? []).map((f) => f.message).join('; ')
            showAlert({
              variant: 'warning',
              autoDismiss: false,
              title: 'Workflow imported with warnings',
              description: warnings || `Created "${importName}" with ${validationResult.warning_count} warning(s)`,
            })
          } else {
            showSuccess({ title: 'Workflow imported', description: `Created "${importName}"` })
          }
          if (data.id) {
            setLocation(`/workflow-builder/${data.id}`)
          }
        },
        onError: (error) => {
          showError({ title: 'Import failed', description: getErrorMessage(error) })
        },
      }
    )
  }, [pendingImport, selectedProject, createWorkflow, showAlert, showSuccess, showError, setLocation, setPendingImport])

  const clearPendingImport = useCallback(() => {
    setPendingImport(null)
  }, [setPendingImport])

  return { handleImportCurrent, handleImportNew, clearPendingImport }
}
