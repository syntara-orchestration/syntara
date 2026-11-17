import { execFile } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import {
  buildUniqueName,
  clickAddConnectedStep,
  clickNode,
  clickSaveAndWait,
  fillCodeEditor,
} from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import {
  apiRequest,
  createProjectViaApi,
  deleteCredentialViaApi,
  deleteProjectViaApi,
  deleteWorkflowViaApi,
  getAuthToken,
  pollExecutionStatus,
} from './utils/api'

const execute = promisify(execFile)
const backend = fileURLToPath(new URL('../../../../backend', import.meta.url))
const fixture = fileURLToPath(new URL('./helpers/kafka-publish-record.py', import.meta.url))
const idResponse = z.object({ id: z.string() })

async function kafkaFixture(action: string, topic: string) {
  return execute('uv', ['run', '--project', backend, 'python', fixture, action, topic], { timeout: 45_000 })
}

test.skip(
  !isSkipWebServerForPlaywrightTests() || process.env.SYNTARA_E2E_KAFKA_PUBLISH_LIVE !== '1',
  'Requires the root Compose Kafka SASL/TLS fixture and a real backend'
)

test('publishes a UI-saved payload template and exact key/header bytes through the real worker', async ({ app }) => {
  test.setTimeout(150_000)
  const name = buildUniqueName('kafka-publish-live')
  const topic = name.replaceAll('-', '_')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  let projectId: string | undefined
  let integrationId: string | undefined
  let workflowId: string | undefined
  const credentialIds: string[] = []
  let topicCreated = false
  try {
    await kafkaFixture('create', topic)
    topicCreated = true
    projectId = (await createProjectViaApi(app, name)).id
    const types = await apiRequest(app, 'get', '/credential_types', { token })
    const kafkaType = z
      .object({ resources: z.array(z.object({ id: z.string(), name: z.string() })) })
      .parse(await types.json())
      .resources.find((type) => type.name === 'Kafka')
    if (!kafkaType) throw new Error('The Kafka credential type is required')
    for (const purpose of ['management', 'runtime']) {
      const response = await apiRequest(app, 'post', '/credentials', {
        token,
        data: {
          name: `${name}-${purpose}`,
          project_id: projectId,
          credential_type_id: kafkaType.id,
          inputs: { username: 'fixture', password: 'disposable-local-only' },
        },
      })
      expect(response.ok()).toBeTruthy()
      credentialIds.push(idResponse.parse(await response.json()).id)
    }
    const caCertificate = await readFile(`${backend}/.secrets/certs/ca.pem`, 'utf8')
    const integration = await apiRequest(app, 'post', '/kafka_integrations', {
      token,
      data: {
        name,
        integration_type: IntegrationTypeEnum.KAFKA,
        enabled: true,
        scope: 'project',
        management_credential_id: credentialIds[0],
        configuration: {
          integration_type: IntegrationTypeEnum.KAFKA,
          bootstrap_servers: [process.env.SYNTARA_E2E_KAFKA_BOOTSTRAP ?? 'host.containers.internal:9093'],
          security_protocol: 'SASL_SSL',
          sasl_mechanism: 'PLAIN',
          ca_certificate: caCertificate,
        },
      },
    })
    expect(integration.ok()).toBeTruthy()
    integrationId = idResponse.parse(await integration.json()).id
    const assignment = await apiRequest(app, 'post', `/integrations/${integrationId}/projects/${projectId}`, { token })
    expect(assignment.ok()).toBeTruthy()
    const workflow = await apiRequest(app, 'post', '/workflows', {
      token,
      data: {
        name,
        project_id: projectId,
        workflow_definition: {
          schema_version: '2.0.0',
          name,
          triggers: [
            {
              id: 'manual',
              type: TriggerTypeEnum.MANUAL_TRIGGER,
              parameters: { input_schema: { type: 'object', properties: { payload: {} } } },
            },
          ],
          nodes: [],
          edges: [],
        },
      },
    })
    expect(workflow.ok()).toBeTruthy()
    workflowId = idResponse.parse(await workflow.json()).id
    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    const panel = await clickAddConnectedStep(app)
    await expect(panel.getByRole('button', { name: 'Kafka Publish', exact: true })).toBeHidden()
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await expect(panel.getByText('Publish a structured message to a Kafka topic.', { exact: true })).toBeVisible()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Publish exact record')
    await app.getByRole('button', { name: 'Integration', exact: true }).click()
    await app.getByRole('option', { name: new RegExp(`^${name}`) }).click()
    await expect(app.getByText('Kafka credential not configured', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeEnabled()
    await app.getByRole('button', { name: 'Runtime credential', exact: true }).click()
    await expect(app.getByRole('option', { name: 'No credential', exact: true })).toBeHidden()
    await app.getByRole('option', { name: `${name}-runtime`, exact: true }).click()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeFocused()
    await app.getByRole('button', { name: 'Change', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toContainText(`${name}-runtime`)
    await app.getByRole('button', { name: 'Cancel', exact: true }).click()
    await app.getByRole('textbox', { name: 'Target topic', exact: true }).fill(topic)
    await fillCodeEditor(app, { value: '${trigger.payload}', label: 'JSON payload', inputMethod: 'insertText' })
    await app.getByRole('button', { name: 'Message key encoding', exact: true }).click()
    await app.getByRole('option', { name: 'Base64 binary', exact: true }).click()
    await app.getByRole('textbox', { name: 'Message key value', exact: true }).fill('AAEC')
    for (const [index, encoding, value] of [
      [1, 'Null (no bytes)', null],
      [2, 'UTF-8 text', ''],
      [3, 'Base64 binary', 'AAEC'],
    ] as const) {
      await app.getByRole('button', { name: 'Add header', exact: true }).click()
      await app.getByRole('textbox', { name: `Header ${index} name`, exact: true }).fill('same')
      await app.getByRole('button', { name: `Header ${index} encoding`, exact: true }).click()
      await app.getByRole('option', { name: encoding, exact: true }).click()
      if (value !== null) await app.getByRole('textbox', { name: `Header ${index} value`, exact: true }).fill(value)
    }
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Publish exact record')
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeEnabled()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('textbox', { name: 'Header 3 value', exact: true })).toHaveValue('AAEC')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    const execution = await apiRequest(app, 'post', '/executions', {
      token,
      data: {
        workflow_id: workflowId,
        trigger_node_id: 'manual',
        input_data: { payload: { outcome: 'completed', items: [true, null, 42] } },
      },
    })
    expect(execution.ok()).toBeTruthy()
    const executionId = idResponse.parse(await execution.json()).id
    await pollExecutionStatus(app, executionId, ['completed'], { token, timeout: 60_000 })
    const record = z
      .object({
        value: z.string(),
        key: z.string().nullable(),
        headers: z.array(z.tuple([z.string(), z.string().nullable()])),
        topic: z.string(),
        partition: z.number(),
        offset: z.string(),
      })
      .parse(JSON.parse((await kafkaFixture('consume', topic)).stdout))
    expect(Buffer.from(record.value, 'base64').toString('utf8')).toBe('{"items":[true,null,42],"outcome":"completed"}')
    expect(record.key).toBe('AAEC')
    expect(record.headers).toEqual([
      ['same', null],
      ['same', ''],
      ['same', 'AAEC'],
    ])
    expect(record.topic).toBe(topic)
    const saved = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    expect(JSON.stringify(await saved.json())).toContain(`"credential_id":"${credentialIds[1]}"`)
    const activities = await apiRequest(app, 'get', `/executions/${executionId}/activities`, { token })
    const output = z
      .object({ resources: z.array(z.object({ output_data: z.unknown() })) })
      .parse(await activities.json()).resources
    expect(output).toContainEqual(
      expect.objectContaining({
        output_data: expect.objectContaining({ topic, partition: record.partition, offset: record.offset }),
      })
    )
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (integrationId) await apiRequest(app, 'delete', `/integrations/${integrationId}`, { token }).catch(() => {})
    for (const id of credentialIds) await deleteCredentialViaApi(app, id)
    if (projectId) await deleteProjectViaApi(app, projectId).catch(() => {})
    if (topicCreated) await kafkaFixture('delete', topic)
  }
})
