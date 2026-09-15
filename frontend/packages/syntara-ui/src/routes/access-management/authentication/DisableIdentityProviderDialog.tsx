import { Content, ContentVariants } from '@patternfly/react-core'
import type { IdentityProvidersAPI } from '@syntara/contracts'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

type DisableIdentityProviderDialogProps = {
  provider: IdentityProvider | null
  isLoading?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function DisableIdentityProviderDialog({
  provider,
  isLoading,
  onConfirm,
  onClose,
}: Readonly<DisableIdentityProviderDialogProps>) {
  if (!provider) return null

  return (
    <SynConfirmationDialog
      isOpen
      onClose={onClose}
      onConfirm={onConfirm}
      title="Disable identity provider?"
      confirmLabel="Disable"
      confirmVariant="primary"
      confirmLoading={isLoading}
    >
      <Content component={ContentVariants.p}>
        You are about to disable the identity provider <strong>{provider.name}</strong>. Users will no longer be able to
        sign in with this provider until it is re-enabled.
      </Content>
      <Content component={ContentVariants.p}>You can re-enable the identity provider at any time.</Content>
    </SynConfirmationDialog>
  )
}
