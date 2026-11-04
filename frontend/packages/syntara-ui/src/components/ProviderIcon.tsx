import { RhUiAutomationIcon, RhUiNetworkIcon } from '@patternfly/react-icons'

import { IdpTypeKey } from '../routes/access-management/authentication/identity-providers/idpTypePresets'

const defaultStyle: React.CSSProperties = { marginRight: 'var(--pf-t--global--spacer--sm)' }

type ProviderIconKey = 'ansible' | null

const IDP_TYPE_TO_ICON: Record<string, ProviderIconKey> = {
  [IdpTypeKey.AAP]: 'ansible',
}

function getProviderIconKey(name: string, idpType?: string | null): ProviderIconKey {
  if (idpType && idpType in IDP_TYPE_TO_ICON) return IDP_TYPE_TO_ICON[idpType]
  const lower = name.toLowerCase()
  if (lower.includes('ansible') || lower.includes('aap')) return 'ansible'
  return null
}

type ProviderIconProps = {
  name: string
  idpType?: string | null
  style?: React.CSSProperties
}

export function ProviderIcon({ name, idpType, style }: Readonly<ProviderIconProps>) {
  if (idpType === IdpTypeKey.CUSTOM) return null
  const key = getProviderIconKey(name, idpType)
  const iconStyle = style ?? defaultStyle

  switch (key) {
    case 'ansible':
      return <RhUiAutomationIcon style={iconStyle} />
    case null:
      return <RhUiNetworkIcon data-testid="network-icon" aria-hidden="true" style={iconStyle} />
  }
}
