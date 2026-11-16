/**
 * Execution plane (OpenShift) rename via Edit name modal, plus delete-then-recreate.
 * Relies on the mock API sole OpenShift seed (see OPENSHIFT_SEED_NAME).
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { findOpenShiftSeed, OPENSHIFT_SEED_NAME, restoreOpenShiftSeed } from './seeds/openshift'
import { createCredentialForIntegrationType, deleteIntegrationViaApi, type SeededCredential } from './seeds/resources'
import { apiRequest, deleteCredentialViaApi, getAuthToken } from './utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()

const WIZARD_URL = '/configuration/integrations/configure'
const INTEGRATIONS_LIST_URL = '/configuration/integrations'

test.describe('Execution plane integration rename', () => {
  // Shared sole OpenShift seed — must not run in parallel.
  test.describe.configure({ mode: 'serial' })
  test.skip(isRealBackend, 'relies on mock API OpenShift seed and singleton recreate')

  test('renames via Edit name modal and PATCHes only the name', async ({ app }) => {
    const updatedName = buildUniqueName('e2e-openshift-renamed')
    const seed = await findOpenShiftSeed(app)
    expect(seed, 'mock OpenShift seed should exist').toBeTruthy()
    const seedId = seed!.id

    try {
      await app.goto(toAppUrl(`${INTEGRATIONS_LIST_URL}/${seedId}`))
      await expect(app.getByRole('heading', { name: OPENSHIFT_SEED_NAME })).toBeVisible({ timeout: 15_000 })

      await expect(app.getByRole('button', { name: 'Edit name' })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Edit integration' })).toHaveCount(0)

      await app.getByRole('button', { name: 'Edit name' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog.getByText('Edit integration name')).toBeVisible()
      await expect(
        dialog.getByText('You can only edit the server name / ID. All other settings are read-only.')
      ).toBeVisible()

      const nameInput = dialog.getByRole('textbox', { name: /Server name \/ ID/i })
      await expect(nameInput).toHaveValue(OPENSHIFT_SEED_NAME)
      await expect(dialog.getByRole('button', { name: 'Save name' })).toBeDisabled()

      const patchPromise = app.waitForRequest(
        (req) => req.method() === 'PATCH' && req.url().includes(`/integrations/${seedId}`)
      )

      await nameInput.clear()
      await nameInput.fill(updatedName)
      await dialog.getByRole('button', { name: 'Save name' }).click()

      const patch = await patchPromise
      expect(JSON.parse(patch.postData() ?? '{}')).toEqual({ name: updatedName })

      await expect(app.getByText('Integration name updated')).toBeVisible({ timeout: 10_000 })
      await expect(app.getByRole('heading', { name: updatedName })).toBeVisible({ timeout: 10_000 })
    } finally {
      const auth = await getAuthToken(app)
      if (auth) {
        await apiRequest(app, 'patch', `/integrations/${seedId}`, {
          token: auth,
          data: { name: OPENSHIFT_SEED_NAME },
        })
      }
    }
  })

  test('delete then recreate allows a new Execution plane integration', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-openshift-recreate')
    const credName = buildUniqueName('e2e-openshift-recreate-cred')
    let credential: SeededCredential | null = null
    let createdIntegrationId: string | null = null

    try {
      const seed = await findOpenShiftSeed(app)
      expect(seed, 'mock OpenShift seed should exist').toBeTruthy()

      await app.goto(toAppUrl(`${INTEGRATIONS_LIST_URL}/${seed!.id}`))
      await expect(app.getByRole('heading', { name: OPENSHIFT_SEED_NAME })).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Integration actions' }).click()
      await app.getByRole('menuitem', { name: /Delete integration/i }).click()

      const deleteDialog = app.getByRole('dialog')
      await expect(deleteDialog.getByText('Delete integration?')).toBeVisible()
      await deleteDialog.getByRole('checkbox').click()
      await deleteDialog.getByRole('button', { name: 'Delete integration' }).click()
      await expect(app.getByText('Integration deleted')).toBeVisible({ timeout: 10_000 })
      await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))

      await app.getByPlaceholder('Filter by name').fill(OPENSHIFT_SEED_NAME)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('row', { name: new RegExp(OPENSHIFT_SEED_NAME) })).toHaveCount(0)

      credential = await createCredentialForIntegrationType(app, {
        name: credName,
        integrationType: 'mcp_server',
      })

      await app.goto(toAppUrl(WIZARD_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      const epOption = app.getByRole('option', { name: /Execution plane infrastructure/i })
      await expect(epOption).toBeEnabled()
      await epOption.click()

      await app.getByRole('textbox', { name: 'Connection name' }).fill(integrationName)
      await app.getByRole('textbox', { name: 'API endpoint' }).fill('https://api.recreated.openshift.example.com:6443')
      await app.getByRole('button', { name: 'Next' }).click()

      await expect(app.getByRole('heading', { level: 2, name: 'Authentication' })).toBeVisible()
      await app.getByRole('button', { name: 'Service account token', exact: true }).click()
      await app.getByRole('option', { name: credName }).click()

      const responsePromise = app.waitForResponse(
        (resp) => resp.request().method() === 'POST' && resp.url().includes('/api/v1/integrations')
      )
      await app.getByRole('button', { name: 'Save integration' }).click()
      const response = await responsePromise
      expect(response.ok()).toBeTruthy()
      createdIntegrationId = ((await response.json()) as { id?: string }).id ?? null

      await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))
      await app.getByPlaceholder('Filter by name').fill(integrationName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('row', { name: new RegExp(integrationName) })).toBeVisible({ timeout: 30_000 })
    } finally {
      if (createdIntegrationId) await deleteIntegrationViaApi(app, createdIntegrationId)
      if (credential) await deleteCredentialViaApi(app, credential.id)
      await restoreOpenShiftSeed(app)
    }
  })
})
