import { IntegrationTypeEnum } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { credentialsClient, integrationsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { projectIdParam } from '../../../utils/queryParams'
import { useAllCredentials } from '../components/useAllCredentials'

import type { TriggerFormData } from './triggerFormSchema'

export function useKafkaSubscribeResources(projectId?: string) {
  const integrations = useQuery({
    queryKey: ['kafka-subscribe-integrations', projectId],
    queryFn: () =>
      fetchAllPages((cursor) =>
        integrationsFetchClient.GET('/kafka_integrations', {
          params: {
            query: {
              enabled: true,
              limit: MAX_PAGE_SIZE,
              cursor,
              ...projectIdParam(projectId),
            },
          },
        })
      ),
  })
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
  return errors
}
