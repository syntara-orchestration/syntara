/**
 * E2E Tests: IdP Configuration Settings
 *
 * Critical paths covered:
 * - Verify the "allow everyone in" IdP setting can be configured via the UI
 */
import { test, expect, toAppUrl } from './fixtures'
import { AAP_OIDC_IDP } from './fixtures/mock-oidc-idps'

test.describe('Allow Everyone In — Setting Configuration', () => {
  test.skip('toggles IdPs allow all authenticated users setting, save, and verify persistence', async ({ app }) => {
    await app.route('**/api/v1/identity_providers/**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(AAP_OIDC_IDP),
        })
      }
      return route.continue()
    })

    await app.goto(toAppUrl(`/system-administration/authentication/identity-providers/${AAP_OIDC_IDP.id}`))
    await expect(app.getByRole('heading', { level: 1, name: 'AAP' })).toBeVisible()
    await app.getByRole('link', { name: /Edit provider/i }).click()

    await expect(app.getByRole('heading', { level: 1, name: 'Edit OIDC provider' })).toBeVisible()
    const allowAllToggle = app.getByRole('switch', { name: /Allow all authenticated/ })
    await expect(allowAllToggle).toBeVisible()
    await expect(allowAllToggle).not.toBeChecked()

    // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
    await allowAllToggle.click({ force: true })
    await expect(allowAllToggle).toBeChecked()

    const aapOidcIdpAllowAllAuthenticated = {
      ...AAP_OIDC_IDP,
      configuration: { ...AAP_OIDC_IDP.configuration, allow_all_authenticated: true },
    }

    await app.route('**/api/v1/identity_providers**', (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'GET') {
        if (url.pathname.endsWith('/identity_providers')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              resources: [aapOidcIdpAllowAllAuthenticated],
            }),
          })
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(aapOidcIdpAllowAllAuthenticated),
        })
      }
      if (route.request().method() === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(aapOidcIdpAllowAllAuthenticated),
        })
      }
      return route.continue()
    })

    await app.getByRole('button', { name: /Save provider/i }).click()

    await expect(app.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
    await expect(app.getByRole('row', { name: /AAP/i })).toBeVisible()

    await app.getByRole('row', { name: /AAP/i }).getByRole('button', { name: /AAP/i }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'AAP' })).toBeVisible()
    // PF6's DescriptionListGroup doesn't add any role attribute, so using getByTestId.
    await expect(app.getByTestId('allow-all-authenticated-field').getByText('Enabled')).toBeVisible()
  })
})
