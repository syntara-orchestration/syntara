import AxeBuilder from '@axe-core/playwright'
import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import { buildUniqueName, clickAddConnectedStep, clickNode, clickSaveAndWait } from './helpers/workflows'
import { apiRequest, createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi, getAuthToken } from './utils/api'

test.use({ viewport: { width: 1440, height: 1100 } })

test('creates, edits and saves a Kafka Publish action', async ({ app }, testInfo) => {
  test.setTimeout(120_000)
  const name = buildUniqueName('kafka-publish')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  let projectId: string | undefined
  let integrationId: string | undefined
  let workflowId: string | undefined
  let credentialId: string | undefined
  try {
    const project = await createProjectViaApi(app, name)
    projectId = project.id
    const types = await apiRequest(app, 'get', '/credential_types', { token })
    expect(types.ok()).toBeTruthy()
    const kafkaType = z
      .object({ resources: z.array(z.object({ id: z.string(), name: z.string() })) })
      .parse(await types.json())
      .resources.find((type) => type.name === 'Kafka')
    if (!kafkaType) throw new Error('Kafka credential type is not seeded')
    const credential = await apiRequest(app, 'post', '/credentials', {
      token,
      data: {
        name: `${name}-runtime`,
        credential_type_id: kafkaType.id,
        project_id: project.id,
        enabled: true,
        inputs: {},
      },
    })
    expect(credential.ok()).toBeTruthy()
    credentialId = z.object({ id: z.string() }).parse(await credential.json()).id
    const integration = await apiRequest(app, 'post', '/kafka_integrations', {
      token,
      data: {
        name,
        integration_type: IntegrationTypeEnum.KAFKA,
        enabled: true,
        scope: 'global',
        configuration: {
          integration_type: IntegrationTypeEnum.KAFKA,
          bootstrap_servers: ['localhost:9093'],
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
    workflowId = z.object({ id: z.string() }).parse(await workflow.json()).id
    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    const panel = await clickAddConnectedStep(app)
    await expect(panel.getByRole('button', { name: 'Kafka Publish', exact: true })).toBeHidden()
    await expect(
      panel.getByText('Run scripts, make API calls, or invoke another published workflow.', { exact: true })
    ).toBeVisible()
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await expect(panel.getByRole('heading', { level: 3 })).toHaveText(['Kafka Publish', 'REST API', 'Script'])
    await expect(panel.getByText('Publish a structured message to a Kafka topic.', { exact: true })).toBeVisible()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Publish outcome')
    await expect(app.getByRole('button', { name: 'Set up connection', exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await app.getByRole('button', { name: 'Integration', exact: true }).click()
    await expect(app.getByRole('option', { name: new RegExp(`^${name}`) })).toContainText('localhost:9093')
    await app.getByRole('option', { name: new RegExp(`^${name}`) }).click()
    await expect(app.getByText('Kafka credential not configured', { exact: true })).toBeVisible()
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toContainText(
      'Select a credential'
    )
    await app.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Set up connection', exact: true })).toBeFocused()
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(app.getByText('Select a runtime Kafka credential', { exact: true })).toBeVisible()
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await app.getByRole('button', { name: 'Runtime credential', exact: true }).click()
    await expect(app.getByRole('option', { name: 'No credential', exact: true })).toBeHidden()
    await app.getByRole('option', { name: `${name}-runtime`, exact: true }).click()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await app.getByRole('textbox', { name: 'Target topic', exact: true }).fill('automation.outcomes')
    await app.getByRole('textbox', { name: 'JSON payload', exact: true }).fill('null')
    await app.getByRole('button', { name: 'Message key encoding', exact: true }).click()
    await app.getByRole('option', { name: 'Base64 binary', exact: true }).click()
    await app.getByRole('textbox', { name: 'Message key value', exact: true }).fill('AAEC')
    await app.getByRole('button', { name: 'Add header', exact: true }).click()
    await app.getByRole('textbox', { name: 'Header 1 name', exact: true }).fill('x')
    await app.getByRole('button', { name: 'Header 1 encoding', exact: true }).click()
    await app.getByRole('option', { name: 'Null (no bytes)', exact: true }).click()
    await app.getByRole('button', { name: 'Add header', exact: true }).click()
    await app.getByRole('textbox', { name: 'Header 2 name', exact: true }).fill('x')
    await app.getByRole('button', { name: 'Add header', exact: true }).click()
    await app.getByRole('textbox', { name: 'Header 3 name', exact: true }).fill('binary')
    await app.getByRole('button', { name: 'Header 3 encoding', exact: true }).click()
    await app.getByRole('option', { name: 'Base64 binary', exact: true }).click()
    await app.getByRole('textbox', { name: 'Header 3 value', exact: true }).fill('AAEC')
    await app.getByRole('button', { name: 'Integration', exact: true }).scrollIntoViewIfNeeded()
    await app.screenshot({ path: testInfo.outputPath('kafka-publish-builder.png'), fullPage: true })
    await app.getByRole('tab', { name: 'Parameters', exact: true }).focus()
    await app.keyboard.press('Tab')
    await app.keyboard.press('Enter')
    await expect(app.getByRole('tab', { name: 'Settings', exact: true })).toHaveAttribute('aria-selected', 'true')
    await app.getByRole('spinbutton', { name: 'Timeout (seconds)', exact: true }).fill('30')
    await app.getByRole('switch', { name: 'Override retry policy', exact: true }).press('Space')
    await app.getByRole('spinbutton', { name: 'Max retries', exact: true }).fill('0')
    await app.getByRole('tab', { name: 'Parameters', exact: true }).click()
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Create', exact: true })).toBeHidden()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeEnabled()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('textbox', { name: 'JSON payload', exact: true })).toHaveValue('null')
    await expect(app.getByRole('textbox', { name: 'Message key value', exact: true })).toHaveValue('AAEC')
    await expect(app.getByRole('button', { name: 'Header 1 encoding', exact: true })).toContainText('Null')
    await expect(app.getByRole('textbox', { name: 'Header 2 name', exact: true })).toHaveValue('x')
    await expect(app.getByRole('textbox', { name: 'Header 2 value', exact: true })).toHaveValue('')
    await expect(app.getByRole('textbox', { name: 'Header 3 value', exact: true })).toHaveValue('AAEC')
    await expect(app.getByRole('button', { name: 'Integration', exact: true })).toBeEnabled()
    await expect(app.getByRole('button', { name: 'Integration', exact: true })).toContainText(name)
    const accessibility = await new AxeBuilder({ page: app })
      .include('[data-step-editor-form]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze()
    expect(accessibility.violations).toEqual([])
    await app.getByRole('textbox', { name: 'Header 2 name', exact: true }).scrollIntoViewIfNeeded()
    await app.screenshot({ path: testInfo.outputPath('kafka-publish-headers.png'), fullPage: true })
    await app.getByRole('textbox', { name: 'Target topic', exact: true }).fill('automation.outcomes.updated')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await clickSaveAndWait(app)
    const saved = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    expect(saved.ok()).toBeTruthy()
    const body: unknown = await saved.json()
    expect(JSON.stringify(body)).toContain('automation.outcomes.updated')
    expect(JSON.stringify(body)).toContain('"max_retries":0')
    expect(JSON.stringify(body)).toContain(`"credential_id":"${credentialId}"`)
    await clickNode(app, 'Publish outcome')
    await app.getByRole('textbox', { name: 'JSON payload', exact: true }).fill('${trigger.payload}')
    await app.getByRole('button', { name: 'Header source', exact: true }).click()
    await app.getByRole('option', { name: 'Full-value template', exact: true }).click()
    await app.getByRole('textbox', { name: 'Headers template', exact: true }).fill('${trigger.payload.headers}')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeEnabled()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('textbox', { name: 'JSON payload', exact: true })).toHaveValue('${trigger.payload}')
    await expect(app.getByRole('textbox', { name: 'Headers template', exact: true })).toHaveValue(
      '${trigger.payload.headers}'
    )
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Update', exact: true })).toBeHidden()
    await app.getByRole('button', { name: /Publish/i }).click()
    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Publish workflow', exact: true }).click()
    await expect(dialog).toBeHidden()
    await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
    await app.getByRole('menuitem', { name: 'Version history', exact: true }).click()
    const versionsResponse = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    const version = z.object({ version: z.object({ version: z.number() }) }).parse(await versionsResponse.json())
      .version.version
    await app
      .getByRole('listitem')
      .filter({ has: app.getByRole('button', { name: `Actions for version ${version}`, exact: true }) })
      .click()
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('button', { name: 'Integration', exact: true })).toBeDisabled()
    await expect(app.getByRole('button', { name: 'Set up connection', exact: true })).toBeHidden()
    await expect(app.getByRole('textbox', { name: 'JSON payload', exact: true })).toBeDisabled()
    await expect(app.getByRole('button', { name: 'Header source', exact: true })).toBeDisabled()
    await expect(app.getByRole('textbox', { name: 'Headers template', exact: true })).toBeDisabled()
    await expect(app.getByRole('button', { name: 'Update', exact: true })).toBeHidden()
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (integrationId) await apiRequest(app, 'delete', `/integrations/${integrationId}`, { token }).catch(() => {})
    if (credentialId) await apiRequest(app, 'delete', `/credentials/${credentialId}`, { token }).catch(() => {})
    if (projectId) await deleteProjectViaApi(app, projectId).catch(() => {})
  }
})
