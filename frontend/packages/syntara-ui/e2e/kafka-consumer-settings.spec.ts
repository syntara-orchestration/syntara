import { readFile } from 'node:fs/promises'

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
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      const saved = app.waitForResponse(
        (response) => response.request().method() === 'PATCH' && response.url().endsWith(`/workflows/${id}`)
      )
      await clickSaveAndWait(app)
      expect((await saved).request().postDataJSON()).toMatchObject({
        workflow_definition: { triggers: [{ parameters: { group_id: 'published-group' } }] },
      })
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

  test('keeps automatic mode through Update, republish, export and publication as a new workflow', async ({ app }) => {
    const connection = await createKafkaConnection(app)
    const createdIds: string[] = []
    const nodes = [
      { id: 'process', name: 'Process', type: 'script', parameters: { language: 'python', code: 'print(1)' } },
    ]
    const edges = [{ from: 'subscribe', to: 'process' }]
    const definitionSchema = z.looseObject({
      triggers: z.array(
        z.looseObject({ id: z.string(), type: z.string(), parameters: z.record(z.string(), z.unknown()) })
      ),
    })
    const detailSchema = z.object({
      kafka_subscription_sources: z.array(z.object({ group_id: z.string(), group_id_is_generated: z.boolean() })),
    })
    try {
      const { id, versionNumber } = await createWorkflowViaApi({
        app,
        name: buildUniqueName('kafka-auto'),
        nodes,
        edges,
        triggers: [
          {
            id: 'subscribe',
            name: 'Automatic consumer',
            type: 'event_subscribe_trigger',
            parameters: {
              integration_id: connection.integrationId,
              credential_id: connection.credentialId,
              topic: 'orders',
              group_id: null,
            },
          },
        ],
      })
      createdIds.push(id)
      await publishWorkflowViaApi(app, id, versionNumber)
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      const token = await getAuthToken(app)
      if (!token) throw new Error('Missing authentication token')
      const detail = detailSchema.parse(await (await apiRequest(app, 'get', `/workflows/${id}`, { token })).json())
      const originalGroup = detail.kafka_subscription_sources[0]?.group_id
      expect(detail.kafka_subscription_sources[0]?.group_id_is_generated).toBe(true)
      await openNodeForEditing(app, 'Automatic consumer')
      await expect(app.getByRole('textbox', { name: GROUP, exact: true })).toHaveValue(originalGroup ?? '')
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      const saved = app.waitForResponse(
        (response) => response.request().method() === 'PATCH' && response.url().endsWith(`/workflows/${id}`)
      )
      await clickSaveAndWait(app)
      expect((await saved).request().postDataJSON()).toMatchObject({
        workflow_definition: { triggers: [{ parameters: { group_id: null } }] },
      })
      await app.getByRole('button', { name: 'Publish workflow', exact: true }).click()
      const published = app.waitForResponse(
        (response) => response.request().method() === 'POST' && response.url().endsWith('/publish')
      )
      await app
        .getByRole('dialog', { name: 'Publish workflow', exact: true })
        .getByRole('button', { name: 'Publish workflow', exact: true })
        .click()
      expect((await published).ok()).toBe(true)
      expect((await published).request().postDataJSON()).not.toHaveProperty('workflow_definition')
      await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
      const downloading = app.waitForEvent('download')
      await app.getByRole('menuitem', { name: 'Export workflow', exact: true }).click()
      const exported = definitionSchema.parse(JSON.parse(await readFile(await (await downloading).path(), 'utf8')))
      expect(exported.triggers[0]?.parameters.group_id).toBeNull()
      const clone = await createWorkflowViaApi({
        app,
        name: buildUniqueName('kafka-auto-import'),
        nodes,
        edges,
        triggers: exported.triggers,
      })
      createdIds.push(clone.id)
      await publishWorkflowViaApi(app, clone.id, clone.versionNumber)
      const cloneDetail = detailSchema.parse(
        await (await apiRequest(app, 'get', `/workflows/${clone.id}`, { token })).json()
      )
      expect(cloneDetail.kafka_subscription_sources[0]?.group_id_is_generated).toBe(true)
      expect(cloneDetail.kafka_subscription_sources[0]?.group_id).not.toBe(originalGroup)
    } finally {
      for (const id of createdIds) await deleteWorkflowViaApi(app, id)
      await deleteIntegrationViaApi(app, connection.integrationId)
      await deleteCredentialViaApi(app, connection.credentialId)
    }
  })

  for (const entry of ['toolbar', 'history', 'list']) {
    test(`offers carry-forward from ${entry} after an older version was published`, async ({ app }, testInfo) => {
      const connection = await createKafkaConnection(app)
      let workflowId: string | undefined
      try {
        const workflowName = buildUniqueName('kafka-stale-group')
        const { id, versionNumber } = await createWorkflowViaApi({
          app,
          name: workflowName,
          nodes: [
            {
              id: 'process',
              name: 'Process order',
              type: 'script',
              parameters: { language: 'python', code: 'print(1)' },
            },
          ],
          edges: [{ from: 'subscribe', to: 'process' }],
          triggers: [
            {
              id: 'subscribe',
              name: 'Orders',
              type: 'event_subscribe_trigger',
              parameters: {
                integration_id: connection.integrationId,
                credential_id: connection.credentialId,
                topic: 'orders',
                group_id: 'established-A',
              },
            },
          ],
        })
        workflowId = id
        const token = await getAuthToken(app)
        if (!token) throw new Error('Missing authentication token')
        const currentResponse = await apiRequest(app, 'get', `/workflows/${id}`, { token })
        expect(currentResponse.ok()).toBe(true)
        const definitionSchema = z.looseObject({
          triggers: z.array(z.looseObject({ id: z.string(), parameters: z.record(z.string(), z.unknown()) })),
        })
        const current = z
          .object({ version: z.object({ workflow_definition: definitionSchema }) })
          .parse(await currentResponse.json())
        const draft = {
          ...current.version.workflow_definition,
          triggers: current.version.workflow_definition.triggers.map((trigger) => ({
            ...trigger,
            parameters: { ...trigger.parameters, group_id: 'draft-B' },
          })),
        }
        const savedResponse = await apiRequest(app, 'patch', `/workflows/${id}`, {
          token,
          data: { workflow_definition: draft },
        })
        expect(savedResponse.ok()).toBe(true)
        const saved = z.object({ current_version: z.number() }).parse(await savedResponse.json())
        await publishWorkflowViaApi(app, id, versionNumber)
        await app.goto(toAppUrl(`/workflow-builder/${id}`))
        await expect(app.getByRole('button', { name: 'Publish workflow', exact: true })).toBeEnabled()
        if (entry === 'list') {
          await app.goto(toAppUrl('/workflows'))
          await app.getByRole('textbox', { name: 'Name filter', exact: true }).fill(workflowName)
          await app.getByRole('button', { name: 'Apply filter', exact: true }).click()
        }
        const openPublish = async () => {
          if (entry === 'list') {
            await app.getByRole('button', { name: `Actions for ${workflowName}`, exact: true }).click()
            await app.getByRole('menuitem', { name: 'Publish workflow', exact: true }).click()
          } else if (entry === 'history') {
            if (
              !(await app
                .getByRole('button', { name: `Actions for version ${saved.current_version}`, exact: true })
                .isVisible())
            ) {
              await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
              await app.getByRole('menuitem', { name: /Version history/i }).click()
            }
            await app.getByRole('button', { name: `Actions for version ${saved.current_version}`, exact: true }).click()
            await app.getByRole('menuitem', { name: 'Publish this version', exact: true }).click()
          } else {
            await app.getByRole('button', { name: 'Publish workflow', exact: true }).click()
          }
        }
        await openPublish()
        const publishDialog = app.getByRole('dialog', { name: 'Publish workflow', exact: true })
        await publishDialog.getByRole('button', { name: 'Publish workflow', exact: true }).click()
        const groupsDialog = app.getByRole('dialog', { name: 'Use the published consumer groups?', exact: true })
        await expect(groupsDialog).toBeVisible()
        await expect(groupsDialog.getByText('draft-B', { exact: true })).toBeVisible()
        await expect(groupsDialog.getByText('established-A', { exact: true })).toBeVisible()
        expect(
          (
            await new AxeBuilder({ page: app })
              .include('[role="dialog"]')
              .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
              .analyze()
          ).violations
        ).toEqual([])
        await app.screenshot({ path: testInfo.outputPath('kafka-group-carry-forward.png'), fullPage: true })
        await groupsDialog.getByRole('button', { name: 'Cancel', exact: true }).click()
        const unchangedResponse = await apiRequest(app, 'get', `/workflows/${id}`, { token })
        const unchanged = z
          .object({ current_version: z.number(), version: z.object({ workflow_definition: definitionSchema }) })
          .parse(await unchangedResponse.json())
        expect(unchanged.current_version).toBe(saved.current_version)
        expect(unchanged.version.workflow_definition.triggers[0]?.parameters.group_id).toBe('draft-B')
        await openPublish()
        await publishDialog.getByRole('button', { name: 'Publish workflow', exact: true }).click()
        await expect(groupsDialog).toBeVisible()
        const published = app.waitForResponse(
          (response) =>
            response.request().method() === 'POST' &&
            response.url().includes(`/workflows/${id}/versions/`) &&
            response.url().endsWith('/publish')
        )
        await groupsDialog.getByRole('button', { name: 'Use published groups and publish', exact: true }).click()
        expect((await published).ok()).toBe(true)
        expect((await published).request().postDataJSON()).toMatchObject({
          workflow_definition: { triggers: [{ parameters: { group_id: 'established-A' } }] },
        })
        const finalResponse = await apiRequest(app, 'get', `/workflows/${id}`, { token })
        const final = z
          .object({ current_version: z.number(), version: z.object({ workflow_definition: definitionSchema }) })
          .parse(await finalResponse.json())
        expect(final.current_version).toBeGreaterThan(saved.current_version)
        expect(final.version.workflow_definition.triggers[0]?.parameters.group_id).toBe('established-A')
        const oldResponse = await apiRequest(app, 'get', `/workflows/${id}/versions/${saved.current_version}`, {
          token,
        })
        const old = z.object({ workflow_definition: definitionSchema }).parse(await oldResponse.json())
        expect(old.workflow_definition.triggers[0]?.parameters.group_id).toBe('draft-B')
        await expect(
          app.getByRole('heading', {
            name: entry === 'history' ? 'Success alert: Version published' : 'Success alert: Workflow published',
            exact: true,
          })
        ).toBeVisible()
        if (entry !== 'list') {
          await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
          const downloadPromise = app.waitForEvent('download')
          await app.getByRole('menuitem', { name: 'Export workflow', exact: true }).click()
          const exported = definitionSchema.parse(
            JSON.parse(await readFile(await (await downloadPromise).path(), 'utf8'))
          )
          expect(exported.triggers[0]?.parameters.group_id).toBe('established-A')
          if (entry === 'history') {
            await openNodeForEditing(app, 'Process order')
            await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Unrelated step edit')
            await app.getByRole('button', { name: 'Update', exact: true }).click()
            const savedAgain = app.waitForResponse(
              (response) => response.request().method() === 'PATCH' && response.url().endsWith(`/workflows/${id}`)
            )
            await clickSaveAndWait(app)
            expect((await savedAgain).ok()).toBe(true)
            expect((await savedAgain).request().postDataJSON()).toMatchObject({
              workflow_definition: { triggers: [{ parameters: { group_id: 'established-A' } }] },
            })
          }
        }
      } finally {
        if (workflowId) await deleteWorkflowViaApi(app, workflowId)
        await deleteIntegrationViaApi(app, connection.integrationId)
        await deleteCredentialViaApi(app, connection.credentialId)
      }
    })
  }
})
