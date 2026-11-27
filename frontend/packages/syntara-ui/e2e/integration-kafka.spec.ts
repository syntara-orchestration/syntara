import { z } from 'zod'

import { test, expect, toAppUrl } from './fixtures'
import { createKafkaCredential } from './helpers/kafka'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi } from './seeds/resources'
import { createProjectViaApi, deleteCredentialViaApi, deleteProjectViaApi } from './utils/api'

function integrationListUrl(name: string) {
  return toAppUrl(`/configuration/integrations?${new URLSearchParams({ 'name[contains]': name })}`)
}

test.describe('Kafka transport configuration', () => {
  test.skip(isSkipWebServerForPlaywrightTests(), 'Uses mock API; no external Kafka broker is required')

  for (const protocol of ['SSL', 'PLAINTEXT'] as const) {
    test(`creates a ${protocol} integration without a SASL credential`, async ({ app }, testInfo) => {
      const name = buildUniqueName(`kafka-${protocol.toLowerCase()}`)
      let id: string | undefined
      try {
        await app.goto(toAppUrl('/configuration/integrations/configure'))
        await app.getByRole('button', { name: 'MCP Server', exact: true }).click()
        await app.getByRole('option', { name: 'Kafka', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
        const brokers = app.getByRole('textbox', { name: 'Bootstrap servers' })
        await brokers.fill('broker.example.com:9093')
        await app.getByRole('button', { name: 'Security protocol' }).click()
        await app.getByRole('option', { name: new RegExp(`^${protocol} —`) }).click()
        await expect(app.getByText('SASL mechanism', { exact: true })).toBeHidden()
        if (protocol === 'SSL') {
          await brokers.fill('https://broker.example.com:9093/path')
          await app.getByRole('button', { name: 'Next', exact: true }).click()
          await expect(brokers).toHaveAttribute('aria-invalid', 'true')
          await expect(app.getByText(/must be host:port with no path/)).toBeVisible()
          await brokers.fill('broker.example.com:9093')
        } else {
          await app.getByRole('button', { name: 'Next', exact: true }).click()
          await expect(app.getByText('Confirm that unencrypted connections are allowed')).toBeVisible()
          await app.getByRole('checkbox', { name: 'Allow unencrypted, unauthenticated connections' }).check()
        }
        await app.getByRole('button', { name: 'Next', exact: true }).click()
        await expect(app.getByRole('button', { name: 'Test connection', exact: true })).not.toHaveAttribute(
          'aria-disabled',
          'true'
        )
        const validation = app.waitForResponse(
          (response) =>
            response.url().endsWith('/api/v1/kafka_integrations/discover') && response.request().method() === 'POST'
        )
        await app.getByRole('button', { name: 'Test connection', exact: true }).click()
        expect((await validation).ok()).toBeTruthy()
        expect(await (await validation).json()).toMatchObject({ success: true })
        const responsePromise = app.waitForResponse(
          (response) => response.url().endsWith('/api/v1/kafka_integrations') && response.request().method() === 'POST'
        )
        await app.getByRole('button', { name: 'Save integration', exact: true }).click()
        const response = await responsePromise
        expect(response.ok()).toBeTruthy()
        const saved = z
          .object({
            id: z.string(),
            configuration: z.object({ security_protocol: z.string(), allow_plaintext: z.boolean() }),
            management_credential_id: z.string().nullable(),
          })
          .parse(await response.json())
        id = saved.id
        expect(saved.configuration.security_protocol).toBe(protocol)
        expect(saved.configuration.allow_plaintext).toBe(protocol === 'PLAINTEXT')
        expect(saved.management_credential_id).toBeNull()
        await app.goto(integrationListUrl(name))
        await expect(app.getByRole('link', { name, exact: true })).toBeVisible()
        await app.getByRole('link', { name, exact: true }).click()
        await expect(app).toHaveURL(new RegExp(`/configuration/integrations/kafka/${id}`))
        await app.reload()
        await expect(app.getByRole('heading', { name, exact: true })).toBeVisible()
        await app.getByRole('button', { name: 'Edit integration', exact: true }).click()
        await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue(name)
        await expect(brokers).toHaveValue('broker.example.com:9093')
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill(`${name}-updated`)
        await brokers.fill('updated.example.com:9094')
        const patchResponse = app.waitForResponse(
          (response) =>
            response.url().endsWith(`/api/v1/kafka_integrations/${id}`) && response.request().method() === 'PATCH'
        )
        await app.getByRole('button', { name: 'Save integration', exact: true }).click()
        expect((await patchResponse).ok()).toBeTruthy()
        await expect(app.getByRole('heading', { name: `${name}-updated`, exact: true })).toBeVisible()
        await app.reload()
        await expect(app.getByRole('heading', { name: `${name}-updated`, exact: true })).toBeVisible()
        await expect(app.getByText('updated.example.com:9094', { exact: true })).toBeVisible()
        await app.screenshot({ path: testInfo.outputPath('kafka-integration-detail.png'), fullPage: true })
        await app.goto(integrationListUrl(`${name}-updated`))
        await expect(app.getByRole('link', { name: `${name}-updated`, exact: true })).toBeVisible()
        const kafkaFilter = new URLSearchParams({ integration_type: 'kafka', 'name[contains]': `${name}-updated` })
        await app.goto(toAppUrl(`/configuration/integrations?${kafkaFilter}`))
        await expect(app.getByRole('link', { name: `${name}-updated`, exact: true })).toBeVisible()
        const row = app
          .getByRole('row')
          .filter({ has: app.getByRole('link', { name: `${name}-updated`, exact: true }) })
        await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
        await app.getByRole('menuitem', { name: 'Delete integration' }).click()
        const confirmation = app.getByRole('dialog')
        await confirmation.getByRole('checkbox').check()
        await confirmation.getByRole('button', { name: 'Delete integration', exact: true }).click()
        await expect(app.getByText('Integration deleted')).toBeVisible()
        await app.goto(integrationListUrl(`${name}-updated`))
        await expect(app.getByRole('heading', { name: 'Integrations', exact: true })).toBeVisible()
        await expect(app.getByRole('link', { name: `${name}-updated`, exact: true })).toHaveCount(0)
        id = undefined
      } finally {
        if (id) await deleteIntegrationViaApi(app, id)
      }
    })
  }

  test('saves and reopens a Kafka SASL management credential as a reference', async ({ app }) => {
    const name = buildUniqueName('kafka-management')
    const project = await createProjectViaApi(app, name)
    const credentialName = `${name}-credential`
    const password = `${name}-disposable`
    let id: string | undefined
    let credentialId: string | undefined
    try {
      credentialId = await createKafkaCredential(app, credentialName, project.id, { username: 'fixture', password })
      await app.goto(toAppUrl('/configuration/integrations/configure'))
      await app.getByRole('button', { name: 'MCP Server', exact: true }).click()
      await app.getByRole('option', { name: 'Kafka', exact: true }).click()
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
      await app.getByRole('textbox', { name: 'Bootstrap servers' }).fill('broker.example.com:9093')
      await app.getByRole('button', { name: 'Next', exact: true }).click()
      const credential = app.getByRole('button', { name: 'Health check credential', exact: true })
      await credential.click()
      await app.getByRole('option', { name: credentialName, exact: true }).click()
      const saved = app.waitForResponse(
        (response) => response.url().endsWith('/api/v1/kafka_integrations') && response.request().method() === 'POST'
      )
      await app.getByRole('button', { name: 'Save integration', exact: true }).click()
      const response = await saved
      expect(response.ok()).toBeTruthy()
      const body: unknown = await response.json()
      id = z.object({ id: z.string() }).parse(body).id
      const submitted: unknown = response.request().postDataJSON()
      expect(submitted).toMatchObject({ management_credential_id: credentialId })
      expect(JSON.stringify(submitted).includes(password)).toBe(false)
      expect(JSON.stringify(body).includes(password)).toBe(false)
      await app.goto(toAppUrl(`/configuration/integrations/kafka/${id}`))
      await expect(app.getByRole('link', { name: credentialName, exact: true })).toBeVisible()
    } finally {
      if (id) await deleteIntegrationViaApi(app, id)
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
      await deleteProjectViaApi(app, project.id)
    }
  })
})
