import { RhUiSecurityIcon } from '@patternfly/react-icons'

import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { createPermissionCheckActivity } from '../../../../stores/workflowFactories'
import { PermissionCheckNodeForm, type PermissionCheckFormData } from '../../node-forms/PermissionCheckNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

/** Palette label for the permission check step. */
export const PERMISSION_CHECK_LABEL = 'Permission check'

/**
 * Register the Permission check step type.
 *
 * Flow control (`logic` category): the step has two output ports, `allowed` and
 * `denied`, and no configuration of its own.
 */
export default function registerPermissionCheckNode() {
  NodeRegistry.register(
    createCustomNode<PermissionCheckFormData>(
      {
        id: RegistryNodeId.LOGIC_PERMISSION_CHECK,
        label: PERMISSION_CHECK_LABEL,
        icon: RhUiSecurityIcon,
        category: 'logic',
        description: 'Routes on whether the previous node was allowed to run for this execution',
        keywords: ['permission', 'denied', 'allowed', 'policy', 'authorization', 'rbac', 'branch'],
        order: 55,
        formComponent: PermissionCheckNodeForm,
      },
      (data, onSuccess, onError) => {
        try {
          const { activityId, activity } = buildNamedActivity(PERMISSION_CHECK_LABEL, data.name, (id, name) =>
            createPermissionCheckActivity(id, name)
          )
          useWorkflowStore.getState().addActivity(activity)
          onSuccess(activityId)
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add permission check step')
        }
      }
    )
  )
}
