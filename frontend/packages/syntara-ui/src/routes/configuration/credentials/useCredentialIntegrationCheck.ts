import type { IntegrationsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { integrationsClient } from '../../../client'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type CredentialIntegrationCheck = {
  affectedIntegrations: Integration[]
  integrationsFetchError: boolean
  isLoadingIntegrations: boolean
}

/**
 * Check which integrations use a credential as their management credential.
 *
 * @param credentialId - Credential ID to check, or null to disable the query.
 * @returns Affected integrations, error flag, and loading state.
 */
export function useCredentialIntegrationCheck(credentialId: string | null): CredentialIntegrationCheck {
  const integrationsQuery = integrationsClient.useQuery(
    'get',
    '/integrations',
    { params: { query: { management_credential_id: credentialId ?? '' } } },
    { enabled: !!credentialId }
  )

  const affectedIntegrations = useMemo(
    () => (integrationsQuery.data?.resources ?? []) as Integration[],
    [integrationsQuery.data?.resources]
  )

  return {
    affectedIntegrations,
    integrationsFetchError: !!integrationsQuery.error,
    isLoadingIntegrations: integrationsQuery.isLoading && !!credentialId,
  }
}
