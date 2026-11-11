import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import { buildUniqueName, clickNode } from './helpers/workflows'
import { apiRequest, createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi, getAuthToken } from './utils/api'

test.use({ viewport: { width: 1440, height: 1100 } })

test('Kafka Subscribe keeps the form stationary while saved resources load', async ({ app }) => {
  const name = buildUniqueName('kafka-subscribe-loading')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  const integrationId = '11111111-1111-4111-8111-111111111111'
  const credentialId = '22222222-2222-4222-8222-222222222222'
  const typeId = '33333333-3333-4333-8333-333333333333'
  let projectId: string | undefined
  let workflowId: string | undefined
  let releaseResources: (() => void) | undefined
  const pendingResources = new Promise<void>((resolve) => {
    releaseResources = resolve
  })

  try {
    const project = await createProjectViaApi(app, name)
    projectId = project.id
    // Persist an unfinished draft; mock only the saved bindings and delayed lookup responses.
    const created = await apiRequest(app, 'post', '/workflows', {
      token,
      data: {
        name,
        project_id: project.id,
        workflow_definition: {
          schema_version: '2.0.0',
          name,
          triggers: [
            { id: 'incoming', name: 'Kafka Subscribe', type: TriggerTypeEnum.EVENT_SUBSCRIBE, parameters: {} },
          ],
          nodes: [],
          edges: [],
        },
      },
    })
    expect(created.ok()).toBeTruthy()
    const workflow = z
      .looseObject({
        id: z.string(),
        version: z.looseObject({ workflow_definition: z.record(z.string(), z.unknown()) }),
      })
      .parse(await created.json())
    workflowId = workflow.id
    await app.route(new RegExp(`/api/v1/workflows/${workflow.id}(?:\\?.*)?$`), (route) =>
      route.fulfill({
        json: {
          ...workflow,
          version: {
            ...workflow.version,
            workflow_definition: {
              ...workflow.version.workflow_definition,
              triggers: [
                {
                  id: 'incoming',
                  name: 'Kafka Subscribe',
                  type: TriggerTypeEnum.EVENT_SUBSCRIBE,
                  parameters: { integration_id: integrationId, credential_id: credentialId, topic: 'orders.created' },
                },
              ],
            },
          },
        },
      })
    )
    await app.route(/\/api\/v1\/kafka_integrations(?:\?.*)?$/, async (route) => {
      await pendingResources
      await route.fulfill({
        json: {
          resources: [
            {
              id: integrationId,
              name: 'Orders Kafka',
              integration_type: IntegrationTypeEnum.KAFKA,
              enabled: true,
              validation_status: 'available',
              configuration: {
                integration_type: IntegrationTypeEnum.KAFKA,
                bootstrap_servers: ['kafka.example.com:9093'],
                security_protocol: 'SSL',
              },
            },
          ],
        },
      })
    })
    await app.route(/\/api\/v1\/credentials(?:\?.*)?$/, async (route) => {
      await pendingResources
      await route.fulfill({
        json: {
          resources: [
            {
              id: credentialId,
              name: 'Orders runtime',
              project_id: project.id,
              enabled: true,
              credential_type_id: typeId,
            },
          ],
        },
      })
    })
    await app.route(/\/api\/v1\/credential_types(?:\?.*)?$/, async (route) => {
      await pendingResources
      await route.fulfill({ json: { resources: [{ id: typeId, name: 'Kafka' }] } })
    })

    await app.goto(toAppUrl(`/workflow-builder/${workflow.id}`))
    await clickNode(app, 'Kafka Subscribe')
    const topic = app.getByRole('textbox', { name: 'Topic', exact: true })
    const access = app.getByRole('button', { name: 'Test runtime access', exact: true })
    await expect(app.getByRole('textbox', { name: 'Kafka Integration', exact: true })).toHaveAttribute(
      'placeholder',
      'Loading Kafka Integrations…'
    )
    await expect(topic).toHaveValue('orders.created')
    await expect(access).toHaveAttribute('aria-disabled', 'true')
    await expect(app.getByText(/Wait for Kafka .* to load/)).toHaveCount(0)
    await expect(app.getByText(/Select an available Kafka Integration, a compatible runtime credential/)).toHaveCount(0)
    const pendingTopic = await topic.boundingBox()
    const pendingAccess = await access.boundingBox()
    if (!pendingTopic || !pendingAccess) throw new Error('Kafka Subscribe controls are not visible')

    releaseResources?.()
    await expect(app.getByRole('textbox', { name: 'Kafka Integration', exact: true })).toHaveValue('Orders Kafka')
    await expect(app.getByText('Orders runtime', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeEnabled()
    await expect(app.getByRole('textbox', { name: 'Kafka runtime credential', exact: true })).toBeHidden()
    await expect(access).not.toHaveAttribute('aria-disabled', 'true')
    const loadedTopic = await topic.boundingBox()
    const loadedAccess = await access.boundingBox()
    if (!loadedTopic || !loadedAccess) throw new Error('Kafka Subscribe controls disappeared after loading')
    expect(loadedTopic.y).toBeCloseTo(pendingTopic.y, 0)
    expect(loadedAccess.y).toBeCloseTo(pendingAccess.y, 0)
  } finally {
    releaseResources?.()
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (projectId) await deleteProjectViaApi(app, projectId)
  }
})
