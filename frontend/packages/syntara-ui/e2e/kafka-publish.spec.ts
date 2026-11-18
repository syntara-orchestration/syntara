import AxeBuilder from '@axe-core/playwright'
import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import {
  buildUniqueName,
  clickAddConnectedStep,
  clickNode,
  clickSaveAndWait,
  fillCodeEditor,
  layoutCanvas,
} from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
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
      panel.getByText('Run scripts, make API calls, invoke another published workflow, or publish messages to Kafka.', {
        exact: true,
      })
    ).toBeVisible()
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await expect(panel.getByRole('heading', { level: 3 })).toHaveText(['Kafka Publish', 'REST API', 'Script'])
    await expect(panel.getByText('Publish a structured message to a Kafka topic.', { exact: true })).toBeVisible()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Publish outcome')
    const deliveryToggle = app.getByRole('button', { name: 'Message delivery behavior', exact: true })
    const deliveryAlert = app.getByRole('region', { name: 'Message delivery behavior', exact: true })
    await expect(deliveryAlert.getByRole('button', { name: 'Message delivery behavior', exact: true })).toBeVisible()
    await deliveryAlert.screenshot({ path: testInfo.outputPath('kafka-publish-delivery-alert-expanded.png') })
    await deliveryToggle.click()
    await expect(deliveryToggle).toHaveAttribute('aria-expanded', 'false')
    await expect(deliveryAlert.getByRole('note')).toHaveCount(0)
    const [alert, toggle, title] = await Promise.all([
      deliveryAlert.boundingBox(),
      deliveryToggle.boundingBox(),
      deliveryAlert.getByRole('heading', { name: /Message delivery behavior/ }).boundingBox(),
    ])
    if (!alert || !toggle || !title) throw new Error('Collapsed delivery alert is not visible')
    expect(toggle.x + toggle.width).toBeLessThan(title.x)
    const collapsedTitleOffset = Math.abs(title.y + title.height / 2 - (alert.y + alert.height / 2))
    expect(collapsedTitleOffset).toBeLessThanOrEqual(3)
    await deliveryAlert.screenshot({ path: testInfo.outputPath('kafka-publish-delivery-alert-collapsed.png') })
    await deliveryToggle.press('Enter')
    await expect(deliveryToggle).toHaveAttribute('aria-expanded', 'true')
    await expect(app.getByText('Drag to reorder headers.', { exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Set up connection', exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await app.getByRole('button', { name: 'Integration', exact: true }).click()
    await expect(app.getByRole('option', { name: new RegExp(`^${name}`) })).toContainText('localhost:9093')
    await app.getByRole('option', { name: new RegExp(`^${name}`) }).click()
    await expect(app.getByText('Kafka credential not configured', { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toContainText(
      'Select a credential'
    )
    await app.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByRole('button', { name: 'Set up connection', exact: true })).toBeFocused()
    await app.getByRole('textbox', { name: 'Target topic', exact: true }).fill('automation.outcomes')
    await fillCodeEditor(app, { value: 'null', label: 'JSON payload', inputMethod: 'insertText' })
    await expect(app.getByTestId('inline-code-editor').locator('[data-mode-id]')).toHaveAttribute(
      'data-mode-id',
      'json'
    )
    await app.getByRole('button', { name: 'Set up connection', exact: true }).click()
    await app.getByRole('button', { name: 'Runtime credential', exact: true }).click()
    await expect(app.getByRole('option', { name: 'No credential', exact: true })).toBeHidden()
    await app.getByRole('option', { name: `${name}-runtime`, exact: true }).click()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await app.getByRole('button', { name: 'Message key encoding', exact: true }).click()
    await app.getByRole('option', { name: 'Base64 binary', exact: true }).click()
    await app.getByRole('textbox', { name: 'Message key value', exact: true }).fill('AAEC')
    await app.getByRole('button', { name: 'Add header', exact: true }).click()
    await app.getByRole('textbox', { name: 'Header 1 name', exact: true }).fill('x')
    await expect(app.getByText('Drag to reorder headers.', { exact: true })).toBeHidden()
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
    await app.getByRole('spinbutton', { name: 'Expected duration (seconds)', exact: true }).fill('2')
    await app.getByRole('switch', { name: 'Override retry policy', exact: true }).press('Space')
    await app.getByRole('spinbutton', { name: 'Max retries', exact: true }).fill('0')
    await app.getByRole('tab', { name: 'Parameters', exact: true }).click()
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Create', exact: true })).toBeHidden()
    const publishNode = app
      .locator('[role="group"][aria-roledescription="node"]')
      .filter({ hasText: 'Publish outcome' })
    await layoutCanvas(app)
    await expect(publishNode.getByText('Target topic', { exact: true })).toBeVisible()
    await expect(publishNode.getByText('automation.outcomes', { exact: true })).toBeVisible()
    await publishNode.screenshot({ path: testInfo.outputPath('kafka-publish-canvas-topic.png') })
    await publishNode.getByRole('button', { name: 'Collapse step details', exact: true }).click()
    await expect(publishNode.getByText('Target topic', { exact: true })).toBeHidden()
    await expect(publishNode.getByText('automation.outcomes', { exact: true })).toBeHidden()
    await publishNode.getByRole('button', { name: 'Expand step details', exact: true }).click()
    await expect(publishNode.getByText('automation.outcomes', { exact: true })).toBeVisible()
    await publishNode.hover()
    await publishNode.getByRole('button', { name: 'Step actions menu', exact: true }).click()
    await app.getByRole('menuitem', { name: 'Disable', exact: true }).click()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('button', { name: 'Change', exact: true })).toBeEnabled()
    await expect(app.getByText(`${name}-runtime`, { exact: true })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Runtime credential', exact: true })).toBeHidden()
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('null')
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
    // Reorder with the pointer, then move a binary header with the keyboard.
    const firstGrip = app.getByRole('button', { name: 'Reorder header 1', exact: true })
    const secondGrip = app.getByRole('button', { name: 'Reorder header 2', exact: true })
    await firstGrip.scrollIntoViewIfNeeded()
    await secondGrip.scrollIntoViewIfNeeded()
    const from = await secondGrip.boundingBox()
    const to = await firstGrip.boundingBox()
    if (!from || !to) throw new Error('Header reorder grips are not visible')
    await app.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
    await app.mouse.down()
    await app.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 20 })
    await app.mouse.up()
    await expect(app.getByRole('button', { name: 'Header 1 encoding', exact: true })).toContainText('UTF-8')
    await expect(app.getByRole('button', { name: 'Header 2 encoding', exact: true })).toContainText('Null')
    const binaryGrip = app.getByRole('button', { name: 'Reorder header 3', exact: true })
    await binaryGrip.scrollIntoViewIfNeeded()
    await binaryGrip.focus()
    // dnd-kit attaches its keyboard listener after pickup; let that setup finish before the next key.
    await binaryGrip.press('Space', { delay: 100 })
    await expect(binaryGrip).toHaveAttribute('aria-pressed', 'true')
    await expect(app.getByText('Header 3 is over position 3 of 3.', { exact: true })).toHaveCount(1)
    await binaryGrip.press('ArrowUp')
    await expect(app.getByText('Header 3 is over position 2 of 3.', { exact: true })).toHaveCount(1)
    await binaryGrip.press('Space')
    await expect(app.getByText('Header 3 dropped at position 2 of 3.', { exact: true })).toHaveCount(1)
    await expect(app.getByRole('textbox', { name: 'Header 2 name', exact: true })).toHaveValue('binary')
    await expect(app.getByRole('textbox', { name: 'Header 2 value', exact: true })).toHaveValue('AAEC')
    await expect(secondGrip).not.toHaveAttribute('aria-pressed', 'true')
    await expect(secondGrip).toBeFocused()
    await app.getByRole('textbox', { name: 'Target topic', exact: true }).fill('automation.outcomes.updated')
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await expect(publishNode.getByText('automation.outcomes.updated', { exact: true })).toBeVisible()
    await clickSaveAndWait(app)
    const saved = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    expect(saved.ok()).toBeTruthy()
    const body: unknown = await saved.json()
    expect(JSON.stringify(body)).toContain('automation.outcomes.updated')
    expect(JSON.stringify(body)).toContain('"max_retries":0')
    expect(JSON.stringify(body)).toContain(`"credential_id":"${credentialId}"`)
    const savedPublish = z
      .object({
        version: z.object({
          workflow_definition: z.object({
            nodes: z.array(
              z.object({
                type: z.string(),
                settings: z.object({ disabled: z.boolean(), expected_duration: z.number() }),
                parameters: z.object({
                  headers: z.array(
                    z.object({
                      name: z.string(),
                      value: z.object({ encoding: z.string(), value: z.string() }).nullable(),
                    })
                  ),
                }),
              })
            ),
          }),
        }),
      })
      .parse(body)
      .version.workflow_definition.nodes.find((node) => node.type === 'kafka_publish')
    expect(savedPublish?.settings.disabled).toBe(true)
    expect(savedPublish?.settings.expected_duration).toBe(2)
    expect(savedPublish?.parameters.headers).toEqual([
      { name: 'x', value: { encoding: 'utf-8', value: '' } },
      { name: 'binary', value: { encoding: 'base64', value: 'AAEC' } },
      { name: 'x', value: null },
    ])
    await clickNode(app, 'Publish outcome')
    await expect(app.getByRole('textbox', { name: 'Header 2 value', exact: true })).toHaveValue('AAEC')
    await expect(app.getByRole('button', { name: 'Header 3 encoding', exact: true })).toContainText('Null')
    await fillCodeEditor(app, { value: '${trigger.payload}', label: 'JSON payload', inputMethod: 'insertText' })
    await expect(app.getByTestId('inline-code-editor').locator('[data-mode-id]')).toHaveAttribute(
      'data-mode-id',
      'plaintext'
    )
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
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('${trigger.payload}')
    await expect(app.getByRole('textbox', { name: 'Headers template', exact: true })).toHaveValue(
      '${trigger.payload.headers}'
    )
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Update', exact: true })).toBeHidden()
    await layoutCanvas(app)
    await publishNode.hover()
    await publishNode.getByRole('button', { name: 'Step actions menu', exact: true }).click()
    // Editing and reopening the disabled step must not silently re-enable it.
    await expect(app.getByRole('menuitem', { name: 'Enable', exact: true })).toBeVisible()
    await app.getByRole('menuitem', { name: 'Enable', exact: true }).click()
    await clickSaveAndWait(app)
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
    const readOnlyPayload = app.getByTestId('inline-code-editor').locator('.monaco-editor')
    await readOnlyPayload.click()
    await app.keyboard.press('ControlOrMeta+A')
    await app.keyboard.insertText('{"must_not_change":true}')
    await expect(readOnlyPayload.locator('.view-lines')).toContainText('${trigger.payload}')
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

test('saves and reopens unfinished Kafka Publish drafts with validation gates', async ({ app }) => {
  test.skip(!isSkipWebServerForPlaywrightTests(), 'Requires backend advisory-save validation findings')
  test.setTimeout(120_000)
  const name = buildUniqueName('kafka-publish-draft')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  let projectId: string | undefined
  let workflowId: string | undefined
  try {
    const project = await createProjectViaApi(app, name)
    projectId = project.id
    const created = await apiRequest(app, 'post', '/workflows', {
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
    expect(created.ok()).toBeTruthy()
    workflowId = z.object({ id: z.string() }).parse(await created.json()).id
    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    const panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Unfinished publish')
    await fillCodeEditor(app, { value: '{"result":', label: 'JSON payload', inputMethod: 'insertText' })
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Create', exact: true })).toBeHidden()
    await clickSaveAndWait(app)
    await expect(app.getByRole('button', { name: 'Run', exact: true })).toHaveAttribute('aria-disabled', 'true')
    await expect(app.getByRole('button', { name: 'Publish workflow', exact: true })).toHaveAttribute(
      'aria-disabled',
      'true'
    )
    await app.reload()
    await clickNode(app, 'Unfinished publish')
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('{"result":')
    await expect(app.getByRole('button', { name: 'Integration', exact: true })).toContainText(
      'Select a Kafka integration'
    )
    await fillCodeEditor(app, { value: '{"edited":', label: 'JSON payload', inputMethod: 'insertText' })
    await app.getByRole('button', { name: 'Update', exact: true }).click()
    await expect(app.getByRole('button', { name: 'Update', exact: true })).toBeHidden()
    await clickSaveAndWait(app)
    await app.reload()
    await clickNode(app, 'Unfinished publish')
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('{"edited":')
    const response = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    const saved = z
      .object({
        has_validation_issues: z.literal(true),
        version: z.object({
          workflow_definition: z.object({
            nodes: z.array(
              z.object({
                parameters: z.record(z.string(), z.unknown()),
                metadata: z.object({ __kafkaPublishPayloadDraft: z.string() }),
              })
            ),
          }),
        }),
      })
      .parse(await response.json())
    expect(saved.version.workflow_definition.nodes[0]?.parameters).not.toHaveProperty('payload')
    expect(saved.version.workflow_definition.nodes[0]?.metadata.__kafkaPublishPayloadDraft).toBe('{"edited":')
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (projectId) await deleteProjectViaApi(app, projectId)
  }
})
