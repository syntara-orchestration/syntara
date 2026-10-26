import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi } from './seeds/resources'

test.describe('Kafka transport configuration', () => {
  test.skip(isSkipWebServerForPlaywrightTests(), 'Uses mock API; no external Kafka broker is required')

  for (const protocol of ['SSL', 'PLAINTEXT'] as const) {
    test(`creates a ${protocol} integration without a SASL credential`, async ({ app }) => {
      const name = buildUniqueName(`kafka-${protocol.toLowerCase()}`)
      let id: string | undefined
      try {
        await app.goto(toAppUrl('/configuration/integrations/configure'))
        await app.getByRole('button', { name: 'MCP Server', exact: true }).click()
        await app.getByRole('option', { name: 'Kafka', exact: true }).click()
        await app.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
        await app.getByRole('textbox', { name: 'Bootstrap servers' }).fill('broker.example.com:9093')
        await app.getByRole('button', { name: 'Security protocol' }).click()
        await app.getByRole('option', { name: new RegExp(`^${protocol} —`) }).click()
        await expect(app.getByText('SASL mechanism', { exact: true })).toBeHidden()
        if (protocol === 'PLAINTEXT') {
          await app.getByRole('button', { name: 'Next', exact: true }).click()
          await expect(app.getByText('Confirm that unencrypted connections are allowed')).toBeVisible()
          await app.getByRole('checkbox', { name: 'Allow unencrypted, unauthenticated connections' }).check()
        }
        await app.getByRole('button', { name: 'Next', exact: true }).click()
        await expect(app.getByRole('button', { name: 'Test connection', exact: true })).not.toHaveAttribute(
          'aria-disabled',
          'true'
        )
        const responsePromise = app.waitForResponse(
          (response) => response.url().endsWith('/api/v2/integrations') && response.request().method() === 'POST'
        )
        await app.getByRole('button', { name: 'Save integration', exact: true }).click()
        const response = await responsePromise
        expect(response.ok()).toBeTruthy()
        const saved = (await response.json()) as {
          id: string
          configuration: { security_protocol: string; allow_plaintext: boolean }
          management_credential_id: string | null
        }
        id = saved.id
        expect(saved.configuration.security_protocol).toBe(protocol)
        expect(saved.configuration.allow_plaintext).toBe(protocol === 'PLAINTEXT')
        expect(saved.management_credential_id).toBeNull()
      } finally {
        if (id) await deleteIntegrationViaApi(app, id)
      }
    })
  }
})
