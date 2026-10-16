import { useMemo } from 'react'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'

export function useBuilderDerivedUiFlags(
  currentWorkflow: WorkflowDefinition | null,
  addStepPanelOpen: boolean,
  stepEditorMode: 'add' | 'edit' | null
) {
  const hasNoWorkflowSteps = useMemo(() => {
    if (!currentWorkflow) {
      return false
    }
    const triggers = currentWorkflow.triggers ?? []
    const activities = currentWorkflow.workflow?.activities ?? []
    return triggers.length === 0 && activities.length === 0
  }, [currentWorkflow])

  const isAddStepPanelOpen = addStepPanelOpen || hasNoWorkflowSteps
  const isStepEditorOpen = stepEditorMode !== null

  return { hasNoWorkflowSteps, isAddStepPanelOpen, isStepEditorOpen }
}
