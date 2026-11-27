import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import {
  createKafkaCredential,
  createKafkaIntegration,
  hasLiveKafka,
  kafkaFixture,
  liveKafkaConfiguration,
  liveKafkaInputs,
} from './helpers/kafka'
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

const idResponse = z.object({ id: z.string() })

test.skip(isSkipWebServerForPlaywrightTests() && !hasLiveKafka, 'Live mode requires the Compose Kafka fixture')

test('runs a Kafka Publish action with a saved payload template and ordered binary headers', async ({ app }) => {
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
    if (hasLiveKafka) {
      await kafkaFixture('create', topic)
      topicCreated = true
    }
    projectId = (await createProjectViaApi(app, name)).id
    for (const purpose of ['management', 'runtime']) {
      credentialIds.push(
        await createKafkaCredential(app, `${name}-${purpose}`, projectId, hasLiveKafka ? liveKafkaInputs : undefined)
      )
    }
    integrationId = await createKafkaIntegration(app, name, {
      projectId,
      managementCredentialId: credentialIds[0],
      configuration: hasLiveKafka ? await liveKafkaConfiguration() : undefined,
    })
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
    await app.getByRole('textbox', { name: 'Topic', exact: true }).fill(topic)
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
    await expect(app.getByRole('textbox', { name: 'Topic', exact: true })).toHaveValue(topic)
    await expect(app.getByRole('button', { name: 'Message key encoding', exact: true })).toContainText('Base64 binary')
    await expect(app.getByRole('textbox', { name: 'Message key value', exact: true })).toHaveValue('AAEC')
    await expect(app.getByRole('button', { name: 'Header 3 encoding', exact: true })).toContainText('Base64 binary')
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
    const saved = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    expect(saved.ok()).toBeTruthy()
    expect(await saved.json()).toMatchObject({
      version: {
        workflow_definition: {
          nodes: expect.arrayContaining([
            expect.objectContaining({
              type: ActivityTypeEnum.KAFKA_PUBLISH,
              parameters: expect.objectContaining({
                credential_id: credentialIds[1],
                topic,
                payload: '${trigger.payload}',
                key: { encoding: 'base64', value: 'AAEC' },
                headers: [
                  { name: 'same', value: null },
                  { name: 'same', value: { encoding: 'utf-8', value: '' } },
                  { name: 'same', value: { encoding: 'base64', value: 'AAEC' } },
                ],
              }),
            }),
          ]),
        },
      },
    })
    if (!hasLiveKafka) return

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
