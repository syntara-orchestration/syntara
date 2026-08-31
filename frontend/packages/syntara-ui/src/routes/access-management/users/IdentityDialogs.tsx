import {
  Content,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Dropdown,
  DropdownItem,
  DropdownList,
  List,
  ListItem,
  MenuToggle,
  type MenuToggleElement,
} from '@patternfly/react-core'
import { RhUiEllipsisVerticalFillIcon, RhUiLinkBrokenIcon, RhUiLinkIcon } from '@patternfly/react-icons'
import { useState } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'

import type { UserIdentity } from './identityUtils'

function DetachConfirmModal({
  identity,
  isDetaching,
  onConfirm,
  onCancel,
}: Readonly<{
  identity: UserIdentity | null
  isDetaching: boolean
  onConfirm: () => void
  onCancel: () => void
}>) {
  return (
    <SynConfirmationDialog
      isOpen={!!identity}
      onClose={onCancel}
      onConfirm={onConfirm}
      title="Disconnect identity?"
      confirmLabel="Disconnect"
      confirmVariant="danger"
      titleIconVariant="warning"
      confirmLoading={isDetaching}
    >
      Disconnecting will remove sign-in access for this identity. You will no longer be able to sign in with it.
      <DescriptionList isHorizontal isCompact style={{ marginTop: 'var(--pf-t--global--spacer--md)' }}>
        <DescriptionListGroup>
          <DescriptionListTerm>Provider</DescriptionListTerm>
          <DescriptionListDescription>{identity?.provider_name}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Issuer</DescriptionListTerm>
          <DescriptionListDescription style={{ wordBreak: 'break-all' }}>{identity?.issuer}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Subject</DescriptionListTerm>
          <DescriptionListDescription style={{ wordBreak: 'break-all' }}>
            {identity?.subject}
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </SynConfirmationDialog>
  )
}

export type ConvertProviderInfo = { name: string; authorizeUrl: string }

export function IdentityDialogs({
  identityToDetach,
  isDetaching,
  onConfirmDetach,
  onCancelDetach,
  convertProvider,
  onCloseConvert,
  onConfirmConvert,
}: Readonly<{
  identityToDetach: UserIdentity | null
  isDetaching: boolean
  onConfirmDetach: () => void
  onCancelDetach: () => void
  convertProvider: ConvertProviderInfo | null
  onCloseConvert: () => void
  onConfirmConvert: () => void
}>) {
  return (
    <>
      <DetachConfirmModal
        identity={identityToDetach}
        isDetaching={isDetaching}
        onConfirm={onConfirmDetach}
        onCancel={onCancelDetach}
      />
      <SynConfirmationDialog
        isOpen={!!convertProvider}
        onClose={onCloseConvert}
        onConfirm={onConfirmConvert}
        title="Link identity provider?"
        confirmLabel="Convert and link"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'convert-to-federated-ack',
          label: 'I understand this action is irreversible',
        }}
      >
        <Content component="p">
          Linking to <strong>{convertProvider?.name}</strong> will permanently convert this account:
        </Content>
        <List>
          <ListItem>Your password will be permanently removed</ListItem>
          <ListItem>You will be signed out and must sign in via the identity provider</ListItem>
          <ListItem>This action cannot be undone</ListItem>
        </List>
      </SynConfirmationDialog>
    </>
  )
}

type ConnectedKebabProps = {
  kind: 'connected'
  isLastIdentity: boolean
  isDetaching: boolean
  onDisconnect: () => void
  /**
   * Defaults to `true` (unlike other `canX` permission props) because disconnecting an
   * identity is a self-service action — users can always disconnect their own identities
   * unless explicitly denied. The `false` case is only hit when viewing another user's
   * profile without `identity:detach` permission.
   */
  canDetach?: boolean
  detachTooltip?: string
}

type DisconnectedKebabProps = {
  kind: 'disconnected'
  isSelf: boolean
  isLocalUser: boolean
  providerName: string
  authorizeUrl: string
  onConvert: (info: ConvertProviderInfo) => void
}

export type IdentityKebabProps = ConnectedKebabProps | DisconnectedKebabProps

function IdentityKebabToggle({
  toggleRef,
  onClick,
  isExpanded,
}: Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  onClick: () => void
  isExpanded: boolean
}>) {
  return (
    <MenuToggle ref={toggleRef} variant="plain" onClick={onClick} isExpanded={isExpanded} aria-label="Identity actions">
      <RhUiEllipsisVerticalFillIcon />
    </MenuToggle>
  )
}

export function IdentityActionsKebab(props: Readonly<IdentityKebabProps>) {
  const [isOpen, setIsOpen] = useState(false)

  let actionItem: React.ReactNode

  if (props.kind === 'connected') {
    const { isLastIdentity, isDetaching, onDisconnect, canDetach = true, detachTooltip } = props
    const isDisconnectDisabled = isLastIdentity || isDetaching || !canDetach

    let disconnectTooltipProps: { content: string } | undefined
    if (isLastIdentity) {
      disconnectTooltipProps = { content: 'Cannot disconnect the only sign-in method' }
    } else if (!canDetach && detachTooltip) {
      disconnectTooltipProps = { content: detachTooltip }
    }

    actionItem = (
      <DropdownItem
        isDanger
        icon={<RhUiLinkBrokenIcon />}
        isAriaDisabled={isDisconnectDisabled}
        tooltipProps={disconnectTooltipProps}
        onClick={
          isDisconnectDisabled
            ? undefined
            : () => {
                onDisconnect()
                setIsOpen(false)
              }
        }
      >
        Disconnect
      </DropdownItem>
    )
  } else {
    const { isSelf, isLocalUser, providerName, authorizeUrl, onConvert } = props
    const handleConnect = () => {
      if (isLocalUser) {
        onConvert({ name: providerName, authorizeUrl })
      } else {
        globalThis.location.href = authorizeUrl
      }
      setIsOpen(false)
    }
    actionItem = (
      <DropdownItem
        icon={<RhUiLinkIcon />}
        isAriaDisabled={!isSelf}
        tooltipProps={!isSelf ? { content: 'Only the user can connect their own identity' } : undefined}
        onClick={isSelf ? handleConnect : undefined}
      >
        Connect
      </DropdownItem>
    )
  }

  return (
    <Dropdown
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      toggle={(toggleRef) => (
        <IdentityKebabToggle toggleRef={toggleRef} onClick={() => setIsOpen((o) => !o)} isExpanded={isOpen} />
      )}
      popperProps={{ position: 'right' }}
    >
      <DropdownList>{actionItem}</DropdownList>
    </Dropdown>
  )
}
