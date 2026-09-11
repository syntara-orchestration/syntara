import { useCallback, useRef } from 'react'

import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import { getErrorMessage } from '../../utils/apiErrors'
import { downloadWorkflowDefinition, parseWorkflowFile, validateFileSize } from '../../utils/downloadWorkflowExport'

import type { BuilderAction } from './builderReducer'
import type { EdgeConnection } from './types/edge'
import { useWorkflowVerification } from './useWorkflowVerification'
import { parseImportedDefinition } from './utils/parseImportedDefinition'
import { buildWorkflowDefinition } from './utils/workflowDefinitionBuilder'

export type PendingImportData = Readonly<{
  workflowDef: WorkflowDefinition
  edges: EdgeConnection[]
  nodePositions: Record<string, { x: number; y: number }>
  name: string
  description: string
}>

type UseWorkflowImportExportOptions = Readonly<{
  dispatch: (action: BuilderAction) => void
  markDirty: () => void
  isNew: boolean
  workflowName: string
  workflowDescription: string
  onPendingImport: (data: PendingImportData) => void
}>

export function applyImportToCanvas(
  data: PendingImportData,
  dispatch: (action: BuilderAction) => void,
  markDirty: () => void,
  showInfo: (options: { title: string; description: string }) => void
): void {
  useWorkflowStore.getState().replaceWorkflowContent(data.workflowDef, data.edges, data.nodePositions)

  if (data.name) {
    const name = data.name.slice(0, 255)
    dispatch({ type: 'SET_WORKFLOW_NAME', payload: name })
    if (data.name.length > 255) {
      showInfo({ title: 'Import note', description: 'Workflow name was truncated to 255 characters' })
    }
  }
  if (data.description) {
    const description = data.description.slice(0, 1024)
    dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: description })
    if (data.description.length > 1024) {
      showInfo({ title: 'Import note', description: 'Workflow description was truncated to 1024 characters' })
    }
  }

  markDirty()
}

export function useWorkflowImportExport({
  dispatch,
  markDirty,
  isNew,
  workflowName,
  workflowDescription,
  onPendingImport,
}: UseWorkflowImportExportOptions) {
  const importFileRef = useRef<HTMLInputElement>(null)
  const { showError } = useAlerts()
  const verification = useWorkflowVerification({ dispatch })

  const handleImportFile = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return

      Promise.resolve()
        .then(() => validateFileSize(file))
        .then(() => file.text())
        .then((content) => {
          const definition = parseWorkflowFile(content, file.name)
          const { workflowDef, edges, nodePositions } = parseImportedDefinition(definition)

          const name =
            definition.name && typeof definition.name === 'string'
              ? definition.name
              : file.name.replace(/\.json$/i, '').replace(/[^a-zA-Z0-9-_]/g, '_')
          const description =
            definition.description && typeof definition.description === 'string' ? definition.description : ''

          const pendingData: PendingImportData = { workflowDef, edges, nodePositions, name, description }

          if (isNew) {
            applyImportToCanvas(pendingData, dispatch, markDirty, showError)
          } else {
            onPendingImport(pendingData)
          }
        })
        .catch((err: unknown) => {
          showError({ title: 'Failed to import workflow', description: getErrorMessage(err) })
        })

      event.target.value = ''
    },
    [dispatch, markDirty, showError, isNew, onPendingImport]
  )

  const handleExport = useCallback(() => {
    const { currentWorkflow, edges, nodePositions } = useWorkflowStore.getState()
    if (!currentWorkflow) {
      dispatch({ type: 'SET_KEBAB_OPEN', payload: false })
      return
    }
    try {
      const { activities } = currentWorkflow.workflow
      const triggers = currentWorkflow.triggers ?? []
      const name = workflowName || 'workflow'
      const description = workflowDescription
      const definition = buildWorkflowDefinition(name, description, activities, triggers, {
        edges,
        nodePositions,
      })
      downloadWorkflowDefinition(definition as Record<string, unknown>, name)
    } catch (err: unknown) {
      showError({ title: 'Failed to export workflow', description: getErrorMessage(err) })
    }
    dispatch({ type: 'SET_KEBAB_OPEN', payload: false })
  }, [dispatch, showError, workflowName, workflowDescription])

  return { importFileRef, handleImportFile, handleExport, ...verification }
}
