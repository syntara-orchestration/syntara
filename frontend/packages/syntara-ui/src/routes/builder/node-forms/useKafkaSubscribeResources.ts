import { IntegrationTypeEnum } from '@syntara/contracts'
import { useMemo } from 'react'

import { credentialsClient } from '../../../client'
import { useAllCredentials } from '../components/useAllCredentials'
import { useAllIntegrations } from '../components/useAllIntegrations'

import type { TriggerFormData } from './triggerFormSchema'

export function useKafkaSubscribeResources(projectId?: string) {
  const integrations = useAllIntegrations(IntegrationTypeEnum.KAFKA, projectId)
  const credentials = useAllCredentials({ projectId })
  const types = credentialsClient.useQuery('get', '/credential_types')
  const visibleIntegrations = useMemo(
    () =>
      integrations.data?.filter((item) => item.integration_type === IntegrationTypeEnum.KAFKA && item.enabled) ?? [],
    [integrations.data]
  )
  const kafkaTypeIds = useMemo(
    () => new Set(types.data?.resources.filter((type) => type.name === 'Kafka').map((type) => type.id)),
    [types.data]
  )
  return { integrations, visibleIntegrations, credentials, types, kafkaTypeIds }
}

export type KafkaSubscribeResources = ReturnType<typeof useKafkaSubscribeResources>

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
    if (resources.credentials.isLoading || resources.types.isPending) {
      errors.runtimeCredentialId = 'Wait for Kafka credentials to load'
    } else if (resources.credentials.error || resources.types.isError) {
      errors.runtimeCredentialId = 'Unable to verify the selected runtime credential'
    } else if (
      !resources.credentials.credentials.some(
        (item) =>
          item.id === data.runtimeCredentialId && item.enabled && resources.kafkaTypeIds.has(item.credential_type_id)
      )
    ) {
      errors.runtimeCredentialId = 'Select an available Kafka runtime credential you can use'
    }
  }
  return errors
}
