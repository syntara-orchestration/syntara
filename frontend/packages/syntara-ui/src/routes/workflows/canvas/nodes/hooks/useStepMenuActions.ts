import {
  RhUiBanIcon,
  RhUiCheckCircleIcon,
  RhUiDuplicateIcon,
  RhUiInformationIcon,
  RhUiPlayIcon,
  RhUiSyncIcon,
  RhUiTrashIcon,
} from '@patternfly/react-icons'
import { useReactFlow } from '@xyflow/react'
import { createElement, useCallback, type ReactNode } from 'react'

import { type StepMenuCategoryUnion, StepMenuCategory } from '../../../../../constants'
import { useAlerts } from '../../../../../providers/alerts'
import { useStepActions } from '../../../../../routes/builder/StepActionsContext'
import { getErrorMessage } from '../../../../../utils/apiErrors'
import { detachPromise } from '../../../../../utils/detachPromise'
import { resolveFlowNodeId } from '../../../../../utils/triggerNodeIds'

// Re-export for convenience
export { StepMenuCategory, type StepMenuCategoryUnion } from '../../../../../constants'

export type StepMenuAction = {
  id: string
  label: string
  onClick: () => void
  icon?: ReactNode
  variant?: 'default' | 'danger'
  separator?: boolean
}

type UseStepMenuActionsOptions = {
  nodeId: string
  stepCategory: StepMenuCategoryUnion
  triggerIndex?: number
  disabled?: boolean
  additionalActions?: StepMenuAction[]
}

type BuilderActionHandlers = {
  onViewDetails: () => void
  onRunStep: () => void
  onToggleDisabled: () => void
  onDuplicate: () => void
  onReplace: () => void
}

function buildBuilderActions(
  stepCategory: StepMenuCategoryUnion,
  disabled: boolean,
  handlers: BuilderActionHandlers
): StepMenuAction[] {
  if (stepCategory === StepMenuCategory.CONTROL_FLOW) {
    return [{ id: 'replace', label: 'Replace', onClick: handlers.onReplace, icon: createElement(RhUiSyncIcon) }]
  }

  const activityActions: StepMenuAction[] =
    stepCategory === StepMenuCategory.ACTIVITY
      ? [
          { id: 'run-step', label: 'Run step', onClick: handlers.onRunStep, icon: createElement(RhUiPlayIcon) },
          {
            id: 'toggle-disabled',
            label: disabled ? 'Enable' : 'Disable',
            onClick: handlers.onToggleDisabled,
            icon: createElement(disabled ? RhUiCheckCircleIcon : RhUiBanIcon),
          },
          {
            id: 'duplicate',
            label: 'Duplicate',
            onClick: handlers.onDuplicate,
            icon: createElement(RhUiDuplicateIcon),
          },
          { id: 'replace', label: 'Replace', onClick: handlers.onReplace, icon: createElement(RhUiSyncIcon) },
        ]
      : []

  return [
    {
      id: 'view-details',
      label: 'View step details',
      onClick: handlers.onViewDetails,
      icon: createElement(RhUiInformationIcon),
    },
    ...activityActions,
  ]
}

function appendDeleteAction(actions: StepMenuAction[], deleteAction: StepMenuAction): StepMenuAction[] {
  if (actions.length === 0) {
    return [deleteAction]
  }
  return [...actions, { id: 'sep-delete', label: '', onClick: () => undefined, separator: true }, deleteAction]
}

/**
 * Custom hook for managing the canvas step kebab menu in the workflow builder.
 * Defines menu items per canvas step category (`StepMenuCategory`).
 *
 * Uses React Flow's deleteElements API to ensure proper edge cleanup and ButtonEdge maintenance.
 *
 * When rendered inside a StepActionsContext.Provider (i.e. within BuilderContent),
 * additional builder-specific actions are automatically included:
 * - View details (all step types)
 * - Run step (activity steps only — currently a placeholder)
 * - Duplicate (activity steps only)
 * - Replace (activity steps only)
 *
 * @param options Configuration options for the step menu (React Flow node id + category)
 * @returns Array of menu actions to display in the kebab menu
 *
 * @example
 * // For activity nodes (Task, Condition, Join, Loop, Parallel)
 * const menuActions = useStepMenuActions({
 *   nodeId: props.data.id,
 *   stepCategory: StepMenuCategory.ACTIVITY,
 * })
 *
 * @example
 * // For trigger nodes
 * const triggerIndex = parseInt(props.id.split('-')[1])
 * const menuActions = useStepMenuActions({
 *   nodeId: props.id,
 *   stepCategory: StepMenuCategory.TRIGGER,
 *   triggerIndex,
 * })
 *
 * @example
 * // With additional custom actions
 * const menuActions = useStepMenuActions({
 *   nodeId: props.data.id,
 *   stepCategory: StepMenuCategory.ACTIVITY,
 *   additionalActions: [
 *     {
 *       id: 'duplicate',
 *       label: 'Duplicate step',
 *       onClick: () => handleDuplicate(),
 *       icon: createElement(RhUiDuplicateIcon),
 *     },
 *   ],
 * })
 */
export function useStepMenuActions(options: UseStepMenuActionsOptions): StepMenuAction[] {
  const { nodeId, stepCategory, triggerIndex, disabled = false, additionalActions = [] } = options
  const { deleteElements } = useReactFlow()
  const { showError } = useAlerts()
  const stepActions = useStepActions()

  const handleDelete = useCallback(() => {
    // Use React Flow's deleteElements to trigger proper cleanup via onNodesDelete
    // This ensures edges are removed and ButtonEdges are recreated correctly
    const flowNodeId = resolveFlowNodeId({ nodeId, stepCategory, triggerIndex })
    detachPromise(deleteElements({ nodes: [{ id: flowNodeId }] }), {
      onReject: (error: unknown) => showError({ title: 'Could not delete step', description: getErrorMessage(error) }),
    })
  }, [stepCategory, nodeId, triggerIndex, deleteElements, showError])

  const handleViewDetails = useCallback(() => {
    stepActions?.onViewDetails(nodeId)
  }, [stepActions, nodeId])

  const handleRunStep = useCallback(() => {
    stepActions?.onRunStep(nodeId)
  }, [stepActions, nodeId])

  const handleDuplicate = useCallback(() => {
    stepActions?.onDuplicate(nodeId)
  }, [stepActions, nodeId])

  const handleReplace = useCallback(() => {
    stepActions?.onReplace(nodeId)
  }, [stepActions, nodeId])

  const handleToggleStepDisabled = useCallback(() => {
    stepActions?.onToggleDisabled(nodeId)
  }, [stepActions, nodeId])

  const deleteAction: StepMenuAction = {
    id: 'delete',
    label: 'Delete',
    onClick: handleDelete,
    variant: 'danger',
    icon: createElement(RhUiTrashIcon),
  }

  const builderActions = stepActions
    ? buildBuilderActions(stepCategory, disabled, {
        onViewDetails: handleViewDetails,
        onRunStep: handleRunStep,
        onToggleDisabled: handleToggleStepDisabled,
        onDuplicate: handleDuplicate,
        onReplace: handleReplace,
      })
    : []

  return appendDeleteAction([...builderActions, ...additionalActions], deleteAction)
}
