import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl, type Page } from './fixtures'
import {
  createKafkaCredential,
  createKafkaIntegration,
  hasLiveKafka,
  kafkaFixture,
  liveKafkaConfiguration,
  liveKafkaInputs,
} from './helpers/kafka'
import { buildUniqueName, clickSaveAndWait, openNodeForEditing } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import {
  apiRequest,
  createProjectViaApi,
  deleteCredentialViaApi,
  deleteProjectViaApi,
  deleteWorkflowViaApi,
} from './utils/api'

const triggerName = 'Kafka Subscribe'
const idResponse = z.object({ id: z.string() })

async function createDraft(app: Page, name: string, projectId: string) {
  const response = await apiRequest(app, 'post', '/workflows', {
    data: {
      name,
      project_id: projectId,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'incoming', name: triggerName, type: TriggerTypeEnum.EVENT_SUBSCRIBE, parameters: {} }],
        nodes: [],
        edges: [],
      },
    },
  })
  expect(response.ok()).toBeTruthy()
  return idResponse.parse(await response.json()).id
}

test('Kafka Subscribe offers only in-scope integrations and saves literal runtime bindings', async ({ app }) => {
  test.skip(isSkipWebServerForPlaywrightTests(), 'Uses inert Kafka integration records from the mock API')
  const name = buildUniqueName('kafka-subscribe')
  const projectIds: string[] = []
  const integrationIds: string[] = []
  const workflowIds: string[] = []
  let credentialId: string | undefined
  const integration = app.getByRole('button', { name: 'Integration', exact: true })
  const topic = app.getByRole('textbox', { name: 'Topic', exact: true })
  const testAccess = app.getByRole('button', { name: 'Test runtime access', exact: true })
  const globalChoice = app.getByRole('option', { name: new RegExp(`^${name}-global`) })
  const projectChoice = app.getByRole('option', { name: new RegExp(`^${name}-project`) })

  try {
    const owner = await createProjectViaApi(app, `${name}-owner`)
    projectIds.push(owner.id)
    const other = await createProjectViaApi(app, `${name}-other`)
    projectIds.push(other.id)
    integrationIds.push(await createKafkaIntegration(app, `${name}-global`))
    const scopedId = await createKafkaIntegration(app, `${name}-project`, { projectId: owner.id })
    integrationIds.push(scopedId)
    credentialId = await createKafkaCredential(app, `${name}-runtime`, owner.id, {
      username: 'fixture',
      password: 'fixture-only',
    })
    const ownerDraft = await createDraft(app, `${name}-owned`, owner.id)
    workflowIds.push(ownerDraft)
    const otherDraft = await createDraft(app, `${name}-elsewhere`, other.id)
    workflowIds.push(otherDraft)

    await app.goto(toAppUrl(`/workflow-builder/${otherDraft}`))
    await openNodeForEditing(app, triggerName)
    await integration.click()
    await expect(globalChoice).toBeVisible()
    await expect(projectChoice).toHaveCount(0)

    await app.goto(toAppUrl(`/workflow-builder/${ownerDraft}`))
    await openNodeForEditing(app, triggerName)
    await expect(testAccess).toHaveAttribute('aria-disabled', 'true')
    await expect(app.getByRole('heading', { name: 'Info alert: Kafka Subscribe behavior', exact: true })).toBeVisible()
    await expect(app.getByRole('region', { name: 'Consumer settings' })).toBeVisible()
    await integration.click()
    await expect(globalChoice).toBeVisible()
    await projectChoice.click()
    await topic.fill('orders.created')
    await expect(testAccess).toHaveAttribute('aria-disabled', 'true')
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await app.getByRole('button', { name: 'Runtime credential', exact: true }).click()
    await app.getByRole('option', { name: `${name}-runtime`, exact: true }).click()
    await expect(testAccess).not.toHaveAttribute('aria-disabled', 'true')
    await topic.fill('orders.*')
    await topic.blur()
    await expect(testAccess).toHaveAttribute('aria-disabled', 'true')
    await topic.fill('orders.created')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await clickSaveAndWait(app)

    const saved = await apiRequest(app, 'get', `/workflows/${ownerDraft}`)
    expect(saved.ok()).toBeTruthy()
    expect(await saved.json()).toMatchObject({
      version: {
        workflow_definition: {
          triggers: [
            {
              parameters: { integration_id: scopedId, credential_id: credentialId, topic: 'orders.created' },
            },
          ],
        },
      },
    })
    await app.reload()
    await openNodeForEditing(app, triggerName)
    await expect(integration).toHaveText(`${name}-project`)
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(topic).toHaveValue('orders.created')
  } finally {
    for (const id of workflowIds) await deleteWorkflowViaApi(app, id)
    for (const id of integrationIds) await apiRequest(app, 'delete', `/integrations/${id}`)
    if (credentialId) await deleteCredentialViaApi(app, credentialId)
    for (const id of projectIds) await deleteProjectViaApi(app, id)
  }
})

test('Kafka Subscribe creates a subscription only after the saved workflow is published', async ({ app }) => {
  test.skip(isSkipWebServerForPlaywrightTests() && !hasLiveKafka, 'Live mode requires the Compose Kafka fixture')
  test.setTimeout(180_000)
  const name = buildUniqueName('kafka-subscribe-publish')
  const topic = name.replaceAll('-', '_')
  let projectId: string | undefined
  let workflowId: string | undefined
  let integrationId: string | undefined
  let topicCreated = false
  const credentialIds: string[] = []
  const hasConsumer = async () => (await kafkaFixture('has-consumer', topic)).stdout.trim() === 'true'
  try {
    if (hasLiveKafka) {
      await kafkaFixture('create', topic)
      topicCreated = true
    }
    projectId = (await createProjectViaApi(app, name)).id
    for (const use of ['management', 'runtime']) {
      credentialIds.push(
        await createKafkaCredential(app, `${name}-${use}`, projectId, hasLiveKafka ? liveKafkaInputs : undefined)
      )
    }
    integrationId = await createKafkaIntegration(app, name, {
      projectId,
      managementCredentialId: credentialIds[0],
      configuration: hasLiveKafka ? await liveKafkaConfiguration() : undefined,
    })
    const response = await apiRequest(app, 'post', '/workflows', {
      data: {
        name,
        project_id: projectId,
        workflow_definition: {
          name,
          schema_version: '2.0.0',
          triggers: [
            {
              id: 'incoming',
              name: triggerName,
              type: TriggerTypeEnum.EVENT_SUBSCRIBE,
              parameters: {
                integration_id: integrationId,
                credential_id: credentialIds[1],
                topic,
              },
            },
          ],
          nodes: [{ id: 'received', type: ActivityTypeEnum.WAIT, parameters: { duration: 1 } }],
          edges: [{ from: 'incoming', to: 'received' }],
        },
      },
    })
    expect(response.ok()).toBeTruthy()
    workflowId = idResponse.parse(await response.json()).id

    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    await openNodeForEditing(app, triggerName)
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Receive Kafka record')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await clickSaveAndWait(app)
    const subscription = z.object({ kafka_subscription_sources: z.array(z.unknown()) })
    const readSources = async () => {
      const detail = await apiRequest(app, 'get', `/workflows/${workflowId}`)
      expect(detail.ok()).toBeTruthy()
      return subscription.parse(await detail.json()).kafka_subscription_sources
    }
    if (hasLiveKafka) expect(await hasConsumer()).toBe(false)
    else expect(await readSources()).toEqual([])

    await app.getByRole('button', { name: 'Publish workflow', exact: true }).click()
    const dialog = app.getByRole('dialog', { name: 'Publish workflow' })
    const published = app.waitForResponse(
      (response) => response.url().includes(`/workflows/${workflowId}/versions/`) && response.url().endsWith('/publish')
    )
    await dialog.getByRole('button', { name: 'Publish workflow', exact: true }).click()
    expect((await published).ok()).toBeTruthy()
    if (!hasLiveKafka) {
      expect(await readSources()).toEqual([
        expect.objectContaining({ trigger_node_id: 'incoming', integration_id: integrationId, topic }),
      ])
      return
    }
    await expect.poll(hasConsumer, { timeout: 60_000, intervals: [1000] }).toBe(true)

    const position = z.object({ partition: z.number(), offset: z.number() })
    const delivery = z.object({
      resources: z.array(
        z.object({
          workflow_id: z.string(),
          status: z.string(),
          input_data: z.object({
            metadata: z.object({ topic: z.string(), partition: z.number(), offset: z.string() }),
          }),
        })
      ),
    })
    const acknowledged = new Set<string>()
    let nextSend = 0
    await expect
      .poll(
        async () => {
          // An assignment may be visible before the worker persists its starting offset.
          if (Date.now() >= nextSend) {
            const sent = position.parse(JSON.parse((await kafkaFixture('send', topic)).stdout))
            acknowledged.add(`${sent.partition}:${sent.offset}`)
            nextSend = Date.now() + 5000
          }
          const response = await apiRequest(app, 'get', `/executions?workflow_id=${workflowId}&limit=20`)
          expect(response.ok()).toBeTruthy()
          return delivery.parse(await response.json()).resources.some(({ workflow_id, status, input_data }) => {
            const source = input_data.metadata
            return (
              workflow_id === workflowId &&
              status === 'completed' &&
              source.topic === topic &&
              acknowledged.has(`${source.partition}:${source.offset}`)
            )
          })
        },
        { timeout: 60_000, intervals: [1000] }
      )
      .toBe(true)
  } finally {
    if (workflowId) {
      await apiRequest(app, 'post', `/workflows/${workflowId}/unpublish`)
      await deleteWorkflowViaApi(app, workflowId)
    }
    if (integrationId) await apiRequest(app, 'delete', `/integrations/${integrationId}`)
    for (const id of credentialIds) await deleteCredentialViaApi(app, id)
    if (projectId) await deleteProjectViaApi(app, projectId)
    if (topicCreated) await kafkaFixture('delete', topic)
  }
})
