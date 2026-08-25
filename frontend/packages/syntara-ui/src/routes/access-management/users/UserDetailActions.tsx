import { Button } from '@patternfly/react-core'
import { RhUiBanIcon, RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { User } from '@syntara/contracts'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { useDialogState } from '../../../hooks/useDialogState'
import { useUserPermissions } from '../useUserPermissions'

const DELETE_USER_ACKNOWLEDGEMENT = {
  checkboxId: 'delete-user-detail-ack',
  label: 'I understand this user will be permanently deleted.',
}

export function UserDetailConfirmationDialogs({
  user,
  revokeDialog,
  deleteDialog,
  onRevoke,
  onDelete,
}: Readonly<{
  user: User
  revokeDialog: ReturnType<typeof useDialogState<User>>
  deleteDialog: ReturnType<typeof useDialogState<User>>
  onRevoke: () => void
  onDelete: () => void
}>) {
  if (user.is_builtin) return null

  return (
    <>
      <NxConfirmationDialog
        isOpen={revokeDialog.isOpen}
        onClose={revokeDialog.close}
        onConfirm={onRevoke}
        title="Revoke user tokens?"
        confirmLabel="Revoke tokens"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        All tokens for <strong>{revokeDialog.item?.username}</strong> will be revoked. The user will be signed out and
        must sign in again.
      </NxConfirmationDialog>
      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={onDelete}
        title="Delete user?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={DELETE_USER_ACKNOWLEDGEMENT}
      >
        The user <strong>{deleteDialog.item?.username}</strong> will be deleted. This cannot be undone.
      </NxConfirmationDialog>
    </>
  )
}

export function UserDetailToolbar({
  permissions,
  showKebabMenu,
  onEdit,
  onRevoke,
  onDelete,
}: Readonly<{
  permissions: ReturnType<typeof useUserPermissions>
  showKebabMenu: boolean
  onEdit: () => void
  onRevoke: () => void
  onDelete: () => void
}>) {
  return (
    <>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          Edit user
        </Button>
      </DisabledWithTooltip>
      {showKebabMenu && (
        <SynKebabMenu
          actions={[
            {
              key: 'revoke',
              title: <IconLabel icon={<RhUiBanIcon />}>Revoke tokens</IconLabel>,
              onClick: permissions.canRevoke ? onRevoke : undefined,
              isAriaDisabled: !permissions.canRevoke,
              tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
            },
            { key: 'separator', isSeparator: true },
            {
              key: 'delete',
              title: <IconLabel icon={<RhUiTrashIcon />}>Delete user</IconLabel>,
              isDanger: true,
              onClick: permissions.canDelete ? onDelete : undefined,
              isAriaDisabled: !permissions.canDelete,
              tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
            },
          ]}
          aria-label="User actions"
        />
      )}
    </>
  )
}
