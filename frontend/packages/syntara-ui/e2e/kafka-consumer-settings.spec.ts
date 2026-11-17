import AxeBuilder from '@axe-core/playwright'
import { z } from 'zod'

import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName, clickSaveAndWait, openNodeForEditing } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi } from './seeds/resources'
import {
  apiRequest,
  createWorkflowViaApi,
  deleteCredentialViaApi,
  ensureProject,
  deleteWorkflowViaApi,
  getAuthToken,
  publishWorkflowViaApi,
} from './utils/api'

const GROUP = 'Consumer group ID'
const EXPRESSION = 'Filter expression (CEL)'
const SOURCE = '  true\n && (true || false)  '

async function createKafkaConnection(app: Page) {
  const token = await getAuthToken(app)
  const project = await ensureProject(app)
  if (!token || !project) throw new Error('Unable to set up Kafka test resources')
  const typesResponse = await apiRequest(app, 'get', '/credential_types', { token })
  expect(typesResponse.ok()).toBe(true)
  const types = z
    .object({ resources: z.array(z.object({ id: z.string(), name: z.string() })) })
    .parse(await typesResponse.json())
  const type = types.resources.find((item) => item.name === 'Kafka')
  if (!type) throw new Error('Kafka credential type is unavailable')
  const credentialResponse = await apiRequest(app, 'post', '/credentials', {
    token,
    data: {
      name: buildUniqueName('consumer-credential'),
      project_id: project.id,
      credential_type_id: type.id,
      inputs: { username: 'mock-user', password: 'mock-password' },
    },
  })
  expect(credentialResponse.ok()).toBe(true)
  const credential = z.object({ id: z.string() }).parse(await credentialResponse.json())
  try {
    const integrationResponse = await apiRequest(app, 'post', '/kafka_integrations', {
      token,
      data: {
        name: buildUniqueName('consumer-integration'),
        integration_type: 'kafka',
        scope: 'global',
        enabled: true,
        configuration: {
          integration_type: 'kafka',
          bootstrap_servers: ['broker.example.com:9093'],
          security_protocol: 'SASL_SSL',
          sasl_mechanism: 'PLAIN',
        },
      },
    })
    expect(integrationResponse.ok()).toBe(true)
    const integration = z.object({ id: z.string() }).parse(await integrationResponse.json())
    return { integrationId: integration.id, credentialId: credential.id }
  } catch (error) {
    await deleteCredentialViaApi(app, credential.id)
    throw error
  }
}

test.describe('Kafka consumer settings', () => {
  test.skip(
    isSkipWebServerForPlaywrightTests(),
    'Exercises draft persistence and publication metadata with the mock API'
  )

  test('saves policies and custom groups, preserves CEL, and resets groups for replacement topics', async ({
    app,
  }, testInfo) => {
    await app.setViewportSize({ width: 1440, height: 1100 })
    const { id } = await createWorkflowViaApi({
      app,
      name: buildUniqueName('kafka-consumer'),
      triggers: [
        {
          id: 'subscribe',
          name: 'Kafka consumer',
          type: 'event_subscribe_trigger',
          parameters: { topic: 'orders', filter: { expression: SOURCE } },
        },
      ],
    })
    try {
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await openNodeForEditing(app, 'Kafka consumer')
      const start = app.getByRole('button', { name: 'Start position', exact: true })
      await expect(start).toHaveText('Latest')
      await start.focus()
      await app.keyboard.press('Enter')
      await app.getByRole('option', { name: 'Earliest', exact: true }).click()
      await expect(start).toBeFocused()
      await app.getByRole('button', { name: 'New partition position', exact: true }).click()
      await app.getByRole('option', { name: 'Latest', exact: true }).click()
      await app.getByRole('button', { name: 'Offset gap policy', exact: true }).click()
      await expect(app.getByRole('option', { name: 'Inherit', exact: true })).toHaveCount(0)
      await app.getByRole('option', { name: 'Fail', exact: true }).click()
      const group = app.getByRole('textbox', { name: GROUP, exact: true })
      await group.fill('bad group')
      await group.blur()
      await expect(group).toHaveAccessibleDescription(/Use 1–512 ASCII/)
      await group.fill('orders.group_1-2')
      await group.blur()
      await expect(group).toHaveAttribute('aria-invalid', 'false')
      await app.getByRole('heading', { name: 'Consumer settings', exact: true }).scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-consumer-settings.png'), fullPage: true })
      await app.emulateMedia({ colorScheme: 'dark' })
      await app.screenshot({ path: testInfo.outputPath('kafka-consumer-settings-dark.png'), fullPage: true })
      await app.emulateMedia({ colorScheme: 'light' })
      const results = await new AxeBuilder({ page: app })
        .include('section[aria-labelledby="kafka-consumer-settings-heading"]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze()
      expect(results.violations).toEqual([])
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      const saved = app.waitForResponse(
        (response) => response.request().method() === 'PATCH' && response.url().endsWith(`/workflows/${id}`)
      )
      await clickSaveAndWait(app)
      expect((await saved).request().postDataJSON()).toMatchObject({
        workflow_definition: {
          triggers: [
            {
              parameters: {
                start: { position: 'earliest', added_partition_position: 'latest', offset_gap_policy: 'fail' },
                group_id: 'orders.group_1-2',
                filter: { expression: SOURCE },
              },
            },
          ],
        },
      })
      await app.reload()
      await openNodeForEditing(app, 'Kafka consumer')
      await expect(app.getByRole('button', { name: 'Start position', exact: true })).toHaveText('Earliest')
      await expect(app.getByRole('button', { name: 'New partition position', exact: true })).toHaveText('Latest')
      await expect(app.getByRole('button', { name: 'Offset gap policy', exact: true })).toHaveText('Fail')
      await expect(group).toHaveValue('orders.group_1-2')
      await expect(app.getByRole('textbox', { name: EXPRESSION, exact: true })).toHaveValue(SOURCE)
      await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('orders.replacement')
      await expect(group).toHaveValue('')
      await group.fill('replacement-group')
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      await clickSaveAndWait(app)
      await app.reload()
      await openNodeForEditing(app, 'Kafka consumer')
      await expect(group).toHaveValue('replacement-group')
      await expect(app.getByRole('button', { name: 'Offset gap policy', exact: true })).toHaveText('Fail')
      await expect(app.getByRole('textbox', { name: EXPRESSION, exact: true })).toHaveValue(SOURCE)
    } finally {
      await deleteWorkflowViaApi(app, id)
    }
  })

  test('locks the group after publication and keeps it locked after unpublishing', async ({ app }, testInfo) => {
    const connection = await createKafkaConnection(app)
    let workflowId: string | undefined
    try {
      const { id, versionNumber } = await createWorkflowViaApi({
        app,
        name: buildUniqueName('kafka-published'),
        triggers: [
          {
            id: 'subscribe',
            name: 'Published Kafka consumer',
            type: 'event_subscribe_trigger',
            parameters: {
              integration_id: connection.integrationId,
              credential_id: connection.credentialId,
              topic: 'orders',
              group_id: 'published-group',
            },
          },
        ],
      })
      workflowId = id
      await publishWorkflowViaApi(app, id, versionNumber)
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await openNodeForEditing(app, 'Published Kafka consumer')
      const group = app.getByRole('textbox', { name: GROUP, exact: true })
      await expect(group).toHaveValue('published-group')
      await expect(group).toBeDisabled()
      await expect(group).toHaveAccessibleDescription(/fixed after its first successful publication/)
      await group.scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-published-group.png'), fullPage: true })
      await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('replacement')
      await expect(group).toBeEnabled()
      await expect(group).toHaveValue('')
      await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('orders')
      await expect(group).toBeDisabled()
      await expect(group).toHaveValue('published-group')
      const token = await getAuthToken(app)
      if (!token) throw new Error('Missing mock authentication token')
      const unpublish = await apiRequest(app, 'post', `/workflows/${id}/unpublish`, { token })
      expect(unpublish.ok()).toBe(true)
      await app.reload()
      await openNodeForEditing(app, 'Published Kafka consumer')
      await expect(group).toBeDisabled()
      await expect(group).toHaveValue('published-group')
    } finally {
      if (workflowId) await deleteWorkflowViaApi(app, workflowId)
      await deleteIntegrationViaApi(app, connection.integrationId)
      await deleteCredentialViaApi(app, connection.credentialId)
    }
  })
})
