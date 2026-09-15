import { getActivityMetadata } from '../../stores/useWorkflowStore'

import { useNodeTypePermissions } from './useNodeTypePermissions'

function resolveEditActivityType(selectedNodeData: unknown): string {
  if (!selectedNodeData || typeof selectedNodeData !== 'object' || !('type' in selectedNodeData)) {
    return ''
  }
  return String((selectedNodeData as { type?: string }).type ?? '')
}

export function useNodeInspectorReadOnly(options: {
  mode: 'add' | 'edit' | null
  selectedNodeData: unknown
  projectId?: string
  isVersionView: boolean
}): { inspectorReadOnly: boolean; readOnlyMessage?: string } {
  const { mode, selectedNodeData, projectId, isVersionView } = options
  const editActivityType = mode === 'edit' ? resolveEditActivityType(selectedNodeData) : ''
  const nodeTypesToCheck = editActivityType ? [editActivityType] : []
  const { permissions, isLoading: nodePermLoading } = useNodeTypePermissions(projectId, nodeTypesToCheck)
  const permissionRedacted = Boolean(getActivityMetadata(selectedNodeData)?.__permissionRedacted)
  const nodeWriteDenied =
    Boolean(editActivityType) &&
    !nodePermLoading &&
    permissions[editActivityType]?.write === false &&
    permissions[editActivityType]?.read !== false
  const inspectorReadOnly = isVersionView || permissionRedacted || nodeWriteDenied

  if (isVersionView) {
    return { inspectorReadOnly }
  }
  if (permissionRedacted) {
    return {
      inspectorReadOnly,
      readOnlyMessage:
        'This step configuration is hidden because your role does not include read access for this node type.',
    }
  }
  if (nodeWriteDenied) {
    return {
      inspectorReadOnly,
      readOnlyMessage: 'This step is read-only for your account due to node-type write permissions.',
    }
  }
  return { inspectorReadOnly }
}
