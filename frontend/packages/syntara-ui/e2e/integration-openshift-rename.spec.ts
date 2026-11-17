/**
 * Execution plane (OpenShift) rename via Edit name modal, plus wizard singleton gating.
 *
 * Rename uses the mock sole OpenShift seed and restores its name in finally.
 * Create-availability is asserted with page.route so this suite never deletes the
 * shared singleton — other fullyParallel mock-API specs keep seeing one OpenShift
 * integration (avoids flaky skips in execution-plane-create and similar).
 */
import { IntegrationTypeEnum } from '@syntara/contracts'

import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { findOpenShiftSeed, OPENSHIFT_SEED_NAME } from './seeds/openshift'
import { apiRequest, getAuthToken } from './utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()

const WIZARD_URL = '/configuration/integrations/configure'
const INTEGRATIONS_LIST_URL = '/configuration/integrations'

/** Fulfill OpenShift existence lookups with an empty list; forward everything else. */
async function routeOpenShiftListEmpty(app: Page): Promise<void> {
  await app.route('**/api/v1/integrations*', async (route) => {
    const request = route.request()
    if (request.method() !== 'GET') {
      await route.continue()
      return
    }
    const url = new URL(request.url())
    if (url.searchParams.get('integration_type') !== IntegrationTypeEnum.OPENSHIFT) {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ resources: [], total: 0 }),
    })
  })
}

test.describe('Execution plane integration rename', () => {
  test.skip(isRealBackend, 'relies on mock API OpenShift seed and page.route fixture isolation')

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

  test('wizard disables Execution plane type when the shared OpenShift seed exists', async ({ app }) => {
    const seed = await findOpenShiftSeed(app)
    expect(seed, 'mock OpenShift seed should exist').toBeTruthy()

    await app.goto(toAppUrl(WIZARD_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

    await app.getByRole('button', { name: 'MCP Server' }).click()
    const epOption = app.getByRole('option', { name: /Execution plane infrastructure/i })
    await expect(epOption).toBeDisabled()
    await expect(app.getByText('Only one Execution plane infrastructure integration is supported.')).toBeVisible()
  })

  test('wizard enables Execution plane type when no OpenShift integration exists', async ({ app }) => {
    // Independent fixture state: do not delete the shared singleton — only this page
    // observes an empty OpenShift list via route interception.
    await routeOpenShiftListEmpty(app)

    try {
      await app.goto(toAppUrl(WIZARD_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      const epOption = app.getByRole('option', { name: /Execution plane infrastructure/i })
      await expect(epOption).toBeEnabled()
      await epOption.click()
      await expect(app.getByRole('textbox', { name: 'Connection name' })).toBeVisible()
    } finally {
      await app.unroute('**/api/v1/integrations*')
    }
  })
})
