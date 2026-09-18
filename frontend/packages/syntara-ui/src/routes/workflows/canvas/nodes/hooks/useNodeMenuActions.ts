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

import { type MenuNodeTypeUnion, MenuNodeType } from '../../../../../constants'
import { useAlerts } from '../../../../../providers/alerts'
import { useNodeActions } from '../../../../../routes/builder/NodeActionsContext'
import { canModifyNodeType, useNodeTypePermissions } from '../../../../../routes/builder/useNodeTypePermissions'
import { resolveWorkflowNodeTypeId } from '../../../../../routes/builder/utils/resolveWorkflowNodeTypeId'
import { useWorkflowStore } from '../../../../../stores/useWorkflowStore'
import { getErrorMessage } from '../../../../../utils/apiErrors'
import { detachPromise } from '../../../../../utils/detachPromise'
import { resolveFlowNodeId } from '../../../../../utils/triggerNodeIds'

// Re-export for convenience
export { MenuNodeType, type MenuNodeTypeUnion } from '../../../../../constants'

export type NodeMenuAction = {
  id: string
  label: string
  onClick: () => void
  icon?: ReactNode
  variant?: 'default' | 'danger'
  separator?: boolean
}

type UseNodeMenuActionsOptions = {
  nodeId: string
  nodeType: MenuNodeTypeUnion
  triggerIndex?: number
  disabled?: boolean
  additionalActions?: NodeMenuAction[]
}

type BuilderActionHandlers = {
  onViewDetails: () => void
  onRunStep: () => void
  onToggleDisabled: () => void
  onDuplicate: () => void
  onReplace: () => void
}

function buildBuilderActions(
  nodeType: MenuNodeTypeUnion,
  disabled: boolean,
  handlers: BuilderActionHandlers
): NodeMenuAction[] {
  if (nodeType === MenuNodeType.CONTROL_FLOW) {
    return [{ id: 'replace', label: 'Replace step', onClick: handlers.onReplace, icon: createElement(RhUiSyncIcon) }]
  }

  const activityActions: NodeMenuAction[] =
    nodeType === MenuNodeType.ACTIVITY
      ? [
          { id: 'run-step', label: 'Run step', onClick: handlers.onRunStep, icon: createElement(RhUiPlayIcon) },
          {
            id: 'toggle-disabled',
            label: disabled ? 'Enable step' : 'Disable step',
            onClick: handlers.onToggleDisabled,
            icon: createElement(disabled ? RhUiCheckCircleIcon : RhUiBanIcon),
          },
          {
            id: 'duplicate',
            label: 'Duplicate step',
            onClick: handlers.onDuplicate,
            icon: createElement(RhUiDuplicateIcon),
          },
          { id: 'replace', label: 'Replace step', onClick: handlers.onReplace, icon: createElement(RhUiSyncIcon) },
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

function appendDeleteAction(actions: NodeMenuAction[], deleteAction: NodeMenuAction): NodeMenuAction[] {
  if (actions.length === 0) {
    return [deleteAction]
  }
  return [...actions, { id: 'sep-delete', label: '', onClick: () => undefined, separator: true }, deleteAction]
}

/**
 * Custom hook for managing the canvas step kebab menu in the workflow builder.
 * Defines menu items per canvas step category (`MenuNodeType`).
 *
 * Uses React Flow's deleteElements API to ensure proper edge cleanup and ButtonEdge maintenance.
 *
 * When rendered inside a NodeActionsContext.Provider (i.e. within BuilderContent),
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
 * const menuActions = useNodeMenuActions({
 *   nodeId: props.data.id,
 *   nodeType: MenuNodeType.ACTIVITY,
 * })
 *
 * @example
 * // For trigger nodes
 * const triggerIndex = parseInt(props.id.split('-')[1])
 * const menuActions = useNodeMenuActions({
 *   nodeId: props.id,
 *   nodeType: MenuNodeType.TRIGGER,
 *   triggerIndex,
 * })
 *
 * @example
 * // With additional custom actions
 * const menuActions = useNodeMenuActions({
 *   nodeId: props.data.id,
 *   nodeType: MenuNodeType.ACTIVITY,
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
export function useNodeMenuActions(options: UseNodeMenuActionsOptions): NodeMenuAction[] {
  const { nodeId, nodeType, triggerIndex, disabled = false, additionalActions = [] } = options
  const { deleteElements } = useReactFlow()
  const { showError } = useAlerts()
  const nodeActions = useNodeActions()
  const projectId = useWorkflowStore((state) => state.projectId)
  const flowNodeId = resolveFlowNodeId({ nodeId, nodeType, triggerIndex })
  const catalogTypeId = resolveWorkflowNodeTypeId(flowNodeId)
  const { permissions, isLoading: nodePermLoading } = useNodeTypePermissions(
    projectId ?? undefined,
    catalogTypeId ? [catalogTypeId] : []
  )
  const canDeleteNode = !catalogTypeId ? false : !nodePermLoading && canModifyNodeType(permissions[catalogTypeId])

  const handleDelete = useCallback(() => {
    if (!canDeleteNode) {
      showError({
        title: 'Cannot delete step',
        description: 'This step cannot be removed with your node-type permissions.',
      })
      return
    }
    // Use React Flow's deleteElements to trigger proper cleanup via onNodesDelete
    // This ensures edges are removed and ButtonEdges are recreated correctly
    detachPromise(deleteElements({ nodes: [{ id: flowNodeId }] }), {
      onReject: (error: unknown) => showError({ title: 'Could not delete step', description: getErrorMessage(error) }),
    })
  }, [canDeleteNode, flowNodeId, deleteElements, showError])

  const handleViewDetails = useCallback(() => {
    nodeActions?.onViewDetails(nodeId)
  }, [nodeActions, nodeId])

  const handleRunStep = useCallback(() => {
    nodeActions?.onRunStep(nodeId)
  }, [nodeActions, nodeId])

  const handleDuplicate = useCallback(() => {
    if (!canDeleteNode) {
      return
    }
    nodeActions?.onDuplicate(nodeId)
  }, [nodeActions, nodeId, canDeleteNode])

  const handleReplace = useCallback(() => {
    nodeActions?.onReplace(nodeId)
  }, [nodeActions, nodeId])

  const handleToggleDisabled = useCallback(() => {
    nodeActions?.onToggleDisabled(nodeId)
  }, [nodeActions, nodeId])

  const deleteAction: NodeMenuAction = {
    id: 'delete',
    label: 'Delete step',
    onClick: handleDelete,
    variant: 'danger',
    icon: createElement(RhUiTrashIcon),
  }

  const builderActions = nodeActions
    ? buildBuilderActions(nodeType, disabled, {
        onViewDetails: handleViewDetails,
        onRunStep: handleRunStep,
        onToggleDisabled: handleToggleDisabled,
        onDuplicate: handleDuplicate,
        onReplace: handleReplace,
      }).filter((action) => {
        if (!canDeleteNode && (action.id === 'duplicate' || action.id === 'replace')) {
          return false
        }
        return true
      })
    : []

  if (!canDeleteNode) {
    return [...builderActions, ...additionalActions]
  }

  return appendDeleteAction([...builderActions, ...additionalActions], deleteAction)
}
