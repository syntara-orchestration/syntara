import { Button } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { detachPromise } from '../../../utils/detachPromise'

import type { useIdentityProviderPermissions } from './useIdentityProviderPermissions'

type IdentityProviderPermissions = ReturnType<typeof useIdentityProviderPermissions>

export function AddProviderButton({ permissions }: Readonly<{ permissions: IdentityProviderPermissions }>) {
  const navigate = useNavigate()
  return (
    <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
      <Button
        variant="primary"
        icon={<RhUiAddIcon />}
        isAriaDisabled={!permissions.canCreate}
        onClick={
          permissions.canCreate
            ? () => detachPromise(navigate({ to: AppRoute.SystemAdministration.Authentication.AddIdentityProvider }))
            : undefined
        }
      >
        Add OIDC provider
      </Button>
    </DisabledWithTooltip>
  )
}

type IdentityProvidersPageToolbarProps = {
  permissions: IdentityProviderPermissions
  showAapButton: boolean
  onAapSetup: () => void
}

/** Page-header actions for the identity providers list (Credentials-style header toolbar). */
export function IdentityProvidersPageToolbar({
  permissions,
  showAapButton,
  onAapSetup,
}: Readonly<IdentityProvidersPageToolbarProps>) {
  return (
    <>
      {showAapButton && (
        <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
          <Button
            variant="secondary"
            isAriaDisabled={!permissions.canCreate}
            onClick={permissions.canCreate ? onAapSetup : undefined}
          >
            Add Ansible Automation Platform
          </Button>
        </DisabledWithTooltip>
      )}
      <AddProviderButton permissions={permissions} />
    </>
  )
}
