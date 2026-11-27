import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

import { IntegrationTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, type Page } from '../fixtures'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'
import { apiRequest } from '../utils/api'

const execute = promisify(execFile)
const backend = fileURLToPath(new URL('../../../../../backend', import.meta.url))
const fixture = fileURLToPath(new URL('./kafka-publish-record.py', import.meta.url))
const idResponse = z.object({ id: z.string() })

export const hasLiveKafka = isSkipWebServerForPlaywrightTests() && process.env.SYNTARA_E2E_KAFKA_PUBLISH_LIVE === '1'

// These credentials belong to the disposable root Compose broker.
export const liveKafkaInputs = { username: 'fixture', password: 'disposable-local-only' }

export async function liveKafkaConfiguration() {
  return {
    integration_type: IntegrationTypeEnum.KAFKA,
    bootstrap_servers: [process.env.SYNTARA_E2E_KAFKA_BOOTSTRAP ?? 'kafka:9092'],
    security_protocol: 'SASL_SSL',
    sasl_mechanism: 'PLAIN',
    ca_certificate: await readFile(`${backend}/.secrets/certs/ca.pem`, 'utf8'),
  }
}

export async function kafkaFixture(action: 'create' | 'delete' | 'consume' | 'send' | 'has-consumer', topic: string) {
  return execute('uv', ['run', '--project', backend, 'python', fixture, action, topic], { timeout: 45_000 })
}

export async function createKafkaCredential(
  app: Page,
  name: string,
  projectId: string,
  inputs: Record<string, string> = {}
) {
  const types = await apiRequest(app, 'get', '/credential_types')
  expect(types.ok()).toBeTruthy()
  const type = z
    .object({ resources: z.array(z.object({ id: z.string(), name: z.string() })) })
    .parse(await types.json())
    .resources.find((item) => item.name === 'Kafka')
  if (!type) throw new Error('The Kafka credential type is required')
  const response = await apiRequest(app, 'post', '/credentials', {
    data: { name, project_id: projectId, credential_type_id: type.id, inputs },
  })
  expect(response.ok()).toBeTruthy()
  return idResponse.parse(await response.json()).id
}

export async function createKafkaIntegration(
  app: Page,
  name: string,
  options: {
    managementCredentialId?: string
    configuration?: Awaited<ReturnType<typeof liveKafkaConfiguration>>
    projectId?: string
  } = {}
) {
  const response = await apiRequest(app, 'post', '/kafka_integrations', {
    data: {
      name,
      integration_type: IntegrationTypeEnum.KAFKA,
      scope: options.projectId ? 'project' : 'global',
      enabled: true,
      management_credential_id: options.managementCredentialId,
      configuration: options.configuration ?? {
        integration_type: IntegrationTypeEnum.KAFKA,
        bootstrap_servers: ['broker.example.com:9093'],
        security_protocol: 'SSL',
      },
    },
  })
  expect(response.ok()).toBeTruthy()
  const { id } = idResponse.parse(await response.json())
  if (options.projectId) {
    const assigned = await apiRequest(app, 'post', `/integrations/${id}/projects/${options.projectId}`)
    if (!assigned.ok()) {
      await apiRequest(app, 'delete', `/integrations/${id}`)
      throw new Error(`Could not assign Kafka integration: HTTP ${assigned.status()}`)
    }
  }
  return id
}
