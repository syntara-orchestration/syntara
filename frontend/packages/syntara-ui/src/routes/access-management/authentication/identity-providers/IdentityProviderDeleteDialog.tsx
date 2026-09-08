import { List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import { useId } from 'react'

import { SynConfirmationDialog } from '../../../../components/dialogs/SynConfirmationDialog'

const DESTRUCTIVE_ACK_LABEL =
  'I understand this identity provider and its linked identities will be permanently deleted.'

export type IdentityProviderDeleteDialogProps = Readonly<{
  isOpen: boolean
  providerName: string
  onClose: () => void
  onConfirm: () => void
}>

/**
 * Delete confirmation for an identity provider — shared by the list page and the detail page.
 */
export function IdentityProviderDeleteDialog({
  isOpen,
  providerName,
  onClose,
  onConfirm,
}: IdentityProviderDeleteDialogProps) {
  const ackCheckboxId = useId()

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Delete identity provider?"
      confirmLabel="Delete"
      confirmVariant="danger"
      titleIconVariant="warning"
      destructiveAcknowledgement={{
        checkboxId: ackCheckboxId,
        label: DESTRUCTIVE_ACK_LABEL,
      }}
    >
      <Stack hasGutter>
        <StackItem>
          The identity provider <strong>{providerName}</strong> will be deleted. This cannot be undone.
        </StackItem>
        <StackItem>This will immediately:</StackItem>
        <StackItem>
          <List>
            <ListItem>Remove all user identities linked to this provider</ListItem>
            <ListItem>Revoke active sessions authenticated via this provider</ListItem>
            <ListItem>Prevent users from signing in with this provider</ListItem>
          </List>
        </StackItem>
      </Stack>
    </SynConfirmationDialog>
  )
}
