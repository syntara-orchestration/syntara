/**
 * E2E Test - Mock OIDC IdP
 *
 * IdPs:
 * - Keycloak
 * - AAP
 */
import type { AuthAPI, IdentityProvidersAPI } from '@syntara/contracts'

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']
type AuthProviderInfo = AuthAPI.components['schemas']['AuthProviderInfo']

export const KEYCLOAK_OIDC_IDP: IdentityProvider = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  created_at: '2025-10-09T12:00:00Z',
  updated_at: '2025-10-09T12:30:00Z',
  labels: {},
  created_by: '770e8400-e29b-41d4-a716-446655440000',
  updated_by: '770e8400-e29b-41d4-a716-446655440000',
  name: 'Keycloak',
  description: null,
  enabled: true,
  configuration: {
    provider_type: 'oidc',
    idp_type: 'custom',
    auto_discovery: true,
    issuer_url: 'https://keycloak-service.example.com',
    client_id: 'mock-client-id',
    redirect_uri: 'http://localhost:8000/api/v1/auth/oidc/callback',
    scopes: 'openid profile email',
    authorization_endpoint: null,
    token_endpoint: null,
    jwks_uri: null,
    userinfo_endpoint: null,
    end_session_endpoint: null,
    enable_rp_initiated_logout: false,
    claim_mapping: {
      subject: 'sub',
      email: 'email',
      username: 'preferred_username',
      first_name: 'given_name',
      last_name: 'family_name',
    },
    group_jmespath_expression: 'groups[*]',
    group_mapping_entries: [
      {
        idp_group_value: 'keycloak-admins',
        nexus_group_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
      },
    ],
    aap_role_mapping_enabled: false,
    disable_tls_verify: false,
  },
}

export const KEYCLOAK_AUTH_PROVIDER: AuthProviderInfo = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  name: 'Keycloak',
  provider_type: 'oidc',
  provider_template: 'custom',
}

export const AAP_OIDC_IDP: IdentityProvider = {
  id: '886ff243-fa0d-4895-8738-a9ece82bf3bf',
  created_at: '2025-10-09T12:00:00Z',
  updated_at: '2025-10-09T12:30:00Z',
  labels: {},
  created_by: '770e8400-e29b-41d4-a716-446655440000',
  updated_by: '770e8400-e29b-41d4-a716-446655440000',
  name: 'AAP',
  description: null,
  enabled: true,
  configuration: {
    provider_type: 'oidc',
    idp_type: 'aap',
    auto_discovery: true,
    issuer_url: 'https://aap.example.com',
    client_id: 'mock-client-id',
    redirect_uri: 'http://localhost:8000/api/v1/auth/oidc/callback',
    scopes: 'read write openid roles',
    authorization_endpoint: null,
    token_endpoint: null,
    jwks_uri: null,
    userinfo_endpoint: null,
    end_session_endpoint: null,
    enable_rp_initiated_logout: true,
    claim_mapping: {
      subject: 'sub',
      email: 'email',
      username: 'preferred_username',
      first_name: 'given_name',
      last_name: 'family_name',
    },
    group_jmespath_expression: '[aap_teams[*].join(/, [organization, name]), aap_organizations[*].name] | []',
    group_mapping_entries: [],
    aap_role_mapping_enabled: true,
    disable_tls_verify: false,
    allow_all_authenticated: false,
  },
}

export const AAP_AUTH_PROVIDER: AuthProviderInfo = {
  id: '886ff243-fa0d-4895-8738-a9ece82bf3bf',
  name: 'AAP',
  provider_type: 'oidc',
  provider_template: 'aap',
}
