import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import type { RoleAssignmentRead } from '../../access/types'

export function UnassignProjectRoleDialog({
  assignment,
  isOpen,
  onClose,
  onConfirm,
}: Readonly<{
  assignment: RoleAssignmentRead | null
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
}>) {
  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Unassign role?"
      confirmLabel="Unassign"
      confirmVariant="danger"
      titleIconVariant="warning"
    >
      This unassigns the role <strong>{assignment?.role_name}</strong> from{' '}
      <strong>{assignment?.principal_name}</strong>. Related permissions will be revoked.
    </SynConfirmationDialog>
  )
}
