/**
 * Pre-configured defaults for known IdP types.
 * Selecting an IdP type pre-fills scopes, claim mappings, and group mapping expression.
 */

export const IdpTypeKey = {
  AAP: 'aap',
  CUSTOM: 'custom',
} as const

export type IdpTypeKeyValue = (typeof IdpTypeKey)[keyof typeof IdpTypeKey]

export type IdpTypePreset = {
  label: string
  scopes: string
  claimMapping: {
    subject: string
    email: string
    username: string
    firstName: string
    lastName: string
  }
  groupMappingExpression: string
  enableRpInitiatedLogout: boolean
  aapRoleMappingEnabled: boolean
}

export const IDP_TYPE_PRESETS: Record<string, IdpTypePreset> = {
  [IdpTypeKey.AAP]: {
    label: 'Ansible Automation Platform',
    scopes: 'read write openid roles',
    claimMapping: {
      subject: 'sub',
      email: 'email',
      username: 'preferred_username',
      firstName: 'given_name',
      lastName: 'family_name',
    },
    groupMappingExpression: "[aap_teams[*].join('/', [organization, name]), aap_organizations[*].name] | []",
    // Keep RP-initiated logout off for AAP: the push-button setup registers a single
    // shared OAuth2 application, and RP logout makes AAP delete every API token tied to
    // it across all users, not just the one logging out.
    enableRpInitiatedLogout: false,
    aapRoleMappingEnabled: true,
  },
  [IdpTypeKey.CUSTOM]: {
    label: 'Custom',
    scopes: 'openid profile email',
    claimMapping: {
      subject: 'sub',
      email: 'email',
      username: 'preferred_username',
      firstName: 'given_name',
      lastName: 'family_name',
    },
    groupMappingExpression: 'groups[*]',
    enableRpInitiatedLogout: false,
    aapRoleMappingEnabled: false,
  },
}

export const IDP_TYPE_OPTIONS = Object.entries(IDP_TYPE_PRESETS).map(([value, preset]) => ({
  value,
  label: preset.label,
}))
