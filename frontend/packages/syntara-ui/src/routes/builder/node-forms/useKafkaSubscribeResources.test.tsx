import type { IntegrationsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { credentialsClient, integrationsFetchClient } from '../../../client'
import { useAllCredentials } from '../components/useAllCredentials'

import { kafkaResourceErrors, useKafkaSubscribeResources } from './useKafkaSubscribeResources'

vi.mock('../../../client', () => ({
  credentialsClient: { useQuery: vi.fn() },
  integrationsFetchClient: { GET: vi.fn() },
}))
vi.mock('../components/useAllCredentials', () => ({ useAllCredentials: vi.fn() }))
const integrationId = '11111111-1111-4111-8111-111111111111'
const credentialId = '22222222-2222-4222-8222-222222222222'
const values = { integrationId, runtimeCredentialId: credentialId }

function wrapper({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
}

beforeEach(() => {
  const integration: IntegrationsAPI.components['schemas']['KafkaIntegrationRead'] = {
    id: integrationId,
    name: 'Kafka',
    integration_type: 'kafka',
    configuration: { integration_type: 'kafka', bootstrap_servers: ['kafka.example.com:9093'] },
    enabled: true,
  }
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { resources: [integration] },
    response: new Response(),
  })
  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: { resources: [{ id: 'kafka-type', name: 'Kafka' }] },
    isPending: false,
    isError: false,
  })
  vi.mocked(useAllCredentials).mockReturnValue({
    credentials: [
      { id: credentialId, project_id: 'project-1', name: 'Runtime', credential_type_id: 'kafka-type', enabled: true },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
})

async function renderResources() {
  const { result } = renderHook(() => useKafkaSubscribeResources('project-1'), { wrapper })
  await waitFor(() => expect(result.current.integrations.isPending).toBe(false))
  return result.current
}

describe('Kafka resource validation', () => {
  it('accepts visible enabled Kafka resources and scopes both selectors to the project', async () => {
    const utils = await renderResources()
    expect(kafkaResourceErrors(values, utils)).toEqual({})
    expect(useAllCredentials).toHaveBeenCalledWith({ projectId: 'project-1' })
    expect(integrationsFetchClient.GET).toHaveBeenCalledWith('/kafka_integrations', {
      params: {
        query: { enabled: true, project_id: 'project-1', cursor: undefined, limit: 100 },
      },
    })
  })
  it('allows omitted references in drafts', async () => {
    expect(kafkaResourceErrors({}, await renderResources())).toEqual({})
  })
  it('rejects an Integration that disappears from the visible list', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({ data: { resources: [] }, response: new Response() })
    expect(kafkaResourceErrors(values, await renderResources()).integrationId).toBe(
      'Select an available Kafka Integration'
    )
  })
})
