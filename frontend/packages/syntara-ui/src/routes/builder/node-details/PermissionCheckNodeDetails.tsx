import type { PermissionCheckActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { PermissionCheckNodeForm, type PermissionCheckFormData } from '../node-forms/PermissionCheckNodeForm'

type PermissionCheckNodeDetailsProps = {
  permissionCheckData: PermissionCheckActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

/**
 * Edit-mode panel for an existing permission check step.
 * The kind has no parameters, so only the step name is editable.
 */
export function PermissionCheckNodeDetails({
  permissionCheckData,
  nodeId,
  onClose,
  onHeaderContentChange,
}: Readonly<PermissionCheckNodeDetailsProps>) {
  const { updateActivity } = useWorkflowStoreActions()

  const initialData: Partial<PermissionCheckFormData> = { name: permissionCheckData.name ?? '' }

  const handleSubmit = (data: PermissionCheckFormData) => {
    updateActivity(nodeId, { ...permissionCheckData, name: data.name, parameters: {} })
    onClose()
  }

  return (
    <PermissionCheckNodeForm
      initialData={initialData}
      onSubmit={handleSubmit}
      onHeaderContentChange={onHeaderContentChange}
    />
  )
}
