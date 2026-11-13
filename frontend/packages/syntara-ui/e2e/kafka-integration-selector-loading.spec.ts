import { IntegrationTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl } from './fixtures'
import { buildUniqueName, clickAddConnectedStep } from './helpers/workflows'
import { apiRequest, createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi, getAuthToken } from './utils/api'

test.use({ viewport: { width: 1440, height: 1100 } })

test('Kafka integration selector keeps its prompt and cached options stable while loading', async ({ app }) => {
  const name = buildUniqueName('kafka-selector-loading')
  const token = await getAuthToken(app)
  if (!token) throw new Error('No test authentication token')
  const integration = {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Orders Kafka',
    integration_type: IntegrationTypeEnum.KAFKA,
    enabled: true,
    validation_status: 'available',
    configuration: {
      integration_type: IntegrationTypeEnum.KAFKA,
      bootstrap_servers: ['broker.example.com:9093'],
      security_protocol: 'SSL',
    },
  }
  let projectId: string | undefined
  let workflowId: string | undefined
  let releaseInitial: (() => void) | undefined
  let releaseRefresh: (() => void) | undefined
  const initialLoad = new Promise<void>((resolve) => {
    releaseInitial = resolve
  })
  const refresh = new Promise<void>((resolve) => {
    releaseRefresh = resolve
  })
  let lookups = 0

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
    await app.route(/\/api\/v1\/kafka_integrations(?:\?.*)?$/, async (route) => {
      lookups += 1
      await (lookups === 1 ? initialLoad : refresh)
      await route.fulfill({ json: { resources: [integration] } })
    })
    await app.route(`**/api/v1/kafka_integrations/${integration.id}`, (route) => route.fulfill({ json: integration }))
    await app.goto(toAppUrl(`/workflow-builder/${workflowId}`))
    const panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    const toggle = app.getByRole('button', { name: 'Integration', exact: true })
    await expect(toggle).toContainText('Select a Kafka integration')
    await expect(toggle).toHaveAttribute('aria-busy', 'true')
    await expect(toggle).toBeDisabled()
    releaseInitial?.()
    await expect(toggle).toBeEnabled()
    await expect(toggle).toContainText('Select a Kafka integration')
    await expect(toggle).not.toHaveAttribute('aria-busy', 'true')
    await toggle.click()
    await app.getByRole('option', { name: /^Orders Kafka/ }).click()
    await expect(toggle).toContainText('Orders Kafka')

    // Parameters unmount while Settings is open. Reopening must retain cached options during the refresh.
    await app.getByRole('tab', { name: 'Settings', exact: true }).click()
    await app.getByRole('tab', { name: 'Parameters', exact: true }).click()
    await expect.poll(() => lookups).toBe(2)
    await expect(toggle).toBeEnabled()
    await expect(toggle).toContainText('Orders Kafka')
    await expect(toggle).not.toHaveAttribute('aria-busy', 'true')
    await toggle.click()
    await expect(app.getByRole('option', { name: /^Orders Kafka/ })).toBeVisible()
    const refreshed = app.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/kafka_integrations')
    )
    releaseRefresh?.()
    expect((await refreshed).ok()).toBeTruthy()
    await expect(toggle).toContainText('Orders Kafka')
    await expect(app.getByRole('option', { name: /^Orders Kafka/ })).toBeVisible()
    await expect(app.getByText('Loading integrations...', { exact: true })).toHaveCount(0)
  } finally {
    releaseInitial?.()
    releaseRefresh?.()
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    if (projectId) await deleteProjectViaApi(app, projectId)
  }
})
