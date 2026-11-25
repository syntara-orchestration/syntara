import { IntegrationTypeEnum, type IntegrationsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { credentialsClient } from '../../../client'
import {
  CREDENTIAL_TYPES_BY_INTEGRATION,
  getKafkaCredentialCompatibilityError,
} from '../../configuration/integrations/integrationFilters'
import { useAllCredentials } from '../components/useAllCredentials'
import { useAllIntegrations } from '../components/useAllIntegrations'

import type { TriggerFormData } from './triggerFormSchema'

type KafkaIntegration = IntegrationsAPI.components['schemas']['KafkaIntegrationRead']

export function useKafkaSubscribeResources(projectId?: string) {
  const integrations = useAllIntegrations(IntegrationTypeEnum.KAFKA, projectId)
  const credentials = useAllCredentials({ projectId })
  const types = credentialsClient.useQuery('get', '/credential_types')
  const visibleIntegrations = useMemo(
    () =>
      integrations.data?.filter(
        (item): item is KafkaIntegration => item.integration_type === IntegrationTypeEnum.KAFKA && item.enabled === true
      ) ?? [],
    [integrations.data]
  )
  const kafkaTypeIds = useMemo(
    () =>
      new Set(
        types.data?.resources
          .filter((type) => CREDENTIAL_TYPES_BY_INTEGRATION[IntegrationTypeEnum.KAFKA].includes(type.name))
          .map((type) => type.id)
      ),
    [types.data]
  )
  return { integrations, visibleIntegrations, credentials, types, kafkaTypeIds }
}

export type KafkaSubscribeResources = ReturnType<typeof useKafkaSubscribeResources>

function runtimeCredentialError(data: Partial<TriggerFormData>, resources: KafkaSubscribeResources) {
  if (resources.credentials.isLoading || resources.types.isPending) return 'Wait for Kafka credentials to load'
  if (resources.credentials.error || resources.types.isError) return 'Unable to verify the selected runtime credential'

  const credential = resources.credentials.credentials.find((item) => item.id === data.runtimeCredentialId)
  if (!credential?.enabled || !resources.kafkaTypeIds.has(credential.credential_type_id)) {
    return 'Select an available Kafka runtime credential you can use'
  }

  const type = resources.types.data?.resources.find((item) => item.id === credential.credential_type_id)
  const configuration = resources.visibleIntegrations.find((item) => item.id === data.integrationId)?.configuration
  return getKafkaCredentialCompatibilityError(
    type?.name,
    configuration?.security_protocol ?? (configuration ? 'SASL_SSL' : undefined),
    configuration?.insecure_skip_tls_verify
  )
}

/** Missing fields are allowed in drafts; explicitly selected resources must be usable. */
export function kafkaResourceErrors(data: Partial<TriggerFormData>, resources: KafkaSubscribeResources) {
  const errors: Partial<Record<'integrationId' | 'runtimeCredentialId', string>> = {}
  if (data.integrationId) {
    if (resources.integrations.isPending) errors.integrationId = 'Wait for Kafka Integrations to load'
    else if (resources.integrations.isError) errors.integrationId = 'Unable to verify the selected Kafka Integration'
    else if (!resources.visibleIntegrations.some((item) => item.id === data.integrationId)) {
      errors.integrationId = 'Select an available Kafka Integration'
    }
  }
  if (data.runtimeCredentialId) {
    const credentialError = runtimeCredentialError(data, resources)
    if (credentialError) errors.runtimeCredentialId = credentialError
  }
  return errors
}
