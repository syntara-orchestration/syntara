import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import { buildUniqueName, clickAddConnectedStep, clickNode, clickSaveAndWait } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { apiRequest, createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi, getAuthToken } from './utils/api'

test.use({ viewport: { width: 1440, height: 1100 } })
test.skip(
  isSkipWebServerForPlaywrightTests(),
  'Uses a mock broker configuration; live delivery has a separate backend fixture test'
)

test('creates, edits and saves a Kafka Publish action', async ({ app }, testInfo) => {
  const name = buildUniqueName('kafka-publish')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  let projectId: string | undefined
  let integrationId: string | undefined
  let workflowId: string | undefined
  try {
    const project = await createProjectViaApi(app, name)
    projectId = project.id
    const integration = await apiRequest(app, 'post', '/kafka_integrations', {
      token,
      data: {
        name,
        integration_type: IntegrationTypeEnum.KAFKA,
        enabled: true,
        scope: 'global',
        configuration: {
          integration_type: IntegrationTypeEnum.KAFKA,
          bootstrap_servers: ['broker.example.com:9093'],
          security_protocol: 'SSL',
        },
      },
    })
    expect(integration.ok()).toBeTruthy()
    integrationId = z.object({ id: z.string() }).parse(await integration.json()).id
    const workflow = await apiRequest(app, 'post', '/workflows', {
      token,
      data: {
        name,
        project_id: project.id,
        workflow_definition: {
          schema_version: '2.0.0',
          name,
          triggers: [{ id: 'manual', type: TriggerTypeEnum.MANUAL_TRIGGER, parameters: {} }],
          nodes: [],
          edges: [],
        },
      },
    })
    expect(workflow.ok()).toBeTruthy()
    workflowId = z.object({ id: z.string() }).parse(await workflow.json()).id
    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    const panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Publish outcome')
    await app.getByRole('button', { name: 'Kafka integration', exact: true }).click()
    await app.getByRole('option', { name: new RegExp(`^${name}`) }).click()
    await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('automation.outcomes')
    await app.getByRole('textbox', { name: 'JSON payload', exact: true }).fill('null')
    await app.getByRole('textbox', { name: 'Message key', exact: true }).fill('{"encoding":"base64","value":"AAEC"}')
    await app
      .getByRole('textbox', { name: 'Message headers', exact: true })
      .fill('[{"name":"x","value":null},{"name":"x","value":{"encoding":"utf-8","value":""}}]')
    await app.getByRole('button', { name: 'Kafka integration', exact: true }).scrollIntoViewIfNeeded()
    await app.screenshot({ path: testInfo.outputPath('kafka-publish-builder.png'), fullPage: true })
    await app.getByRole('tab', { name: 'Parameters', exact: true }).focus()
    await app.keyboard.press('Tab')
    await app.keyboard.press('Enter')
    await expect(app.getByRole('tab', { name: 'Settings', exact: true })).toHaveAttribute('aria-selected', 'true')
    await app.getByRole('tab', { name: 'Parameters', exact: true }).click()
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Create', exact: true })).toBeHidden()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('textbox', { name: 'JSON payload', exact: true })).toHaveValue('null')
    await expect(app.getByRole('textbox', { name: 'Message headers', exact: true })).toHaveValue(
      JSON.stringify(
        [
          { name: 'x', value: null },
          { name: 'x', value: { encoding: 'utf-8', value: '' } },
        ],
        null,
        2
      )
    )
    await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('automation.outcomes.updated')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await clickSaveAndWait(app)
    const saved = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    expect(saved.ok()).toBeTruthy()
    const body: unknown = await saved.json()
    expect(JSON.stringify(body)).toContain('automation.outcomes.updated')
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (integrationId) await apiRequest(app, 'delete', `/kafka_integrations/${integrationId}`, { token })
    if (projectId) await deleteProjectViaApi(app, projectId)
  }
})
