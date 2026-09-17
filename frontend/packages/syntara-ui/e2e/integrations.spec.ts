import { test, expect, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { createIntegrationViaApi, deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { getAuthToken } from './utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()

test('user configures an integration and verifies it appears', async ({ app }) => {
  const integrationName = buildUniqueName('e2e-integration')
  let seededIntegration: SeededIntegration | null = null

  try {
    const token = await getAuthToken(app)
    seededIntegration = await createIntegrationViaApi(app, { name: integrationName, token: token ?? undefined })
    expect(seededIntegration, 'Failed to create integration via API').toBeTruthy()

    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    await expect(app).toHaveTitle(`Integrations | ${APP_TITLE}`)

    await app.getByPlaceholder('Filter by name').fill(integrationName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const integrationRow = app.getByRole('row', { name: new RegExp(integrationName) })
    await expect(integrationRow).toBeVisible({ timeout: 30000 })
  } finally {
    if (seededIntegration) {
      await deleteIntegrationViaApi(app, seededIntegration.id)
    }
  }
})

test.describe('Integration status display', () => {
  test.skip(isRealBackend, 'relies on mock API seed data')

  test('error status badge shows validation error tooltip on hover', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    const jiraRow = app.getByRole('row', { name: /Jira Integration/ })
    await expect(jiraRow).toBeVisible()

    const errorLabel = jiraRow.getByText('Error')
    await errorLabel.hover()
    await expect(app.getByRole('tooltip')).toHaveText('Connection refused')
  })

  test('available status badge does not show tooltip on hover', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    const copilotRow = app.getByRole('row', { name: /GitHub Copilot/ })
    await expect(copilotRow).toBeVisible()

    const availableLabel = copilotRow.getByText('Available')
    await availableLabel.hover()
    await expect(app.getByRole('tooltip')).not.toBeAttached({ timeout: 1000 })
  })
})
