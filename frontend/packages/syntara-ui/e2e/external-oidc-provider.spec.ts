/**
 * E2E Tests: IdP configuration and login form validation — Gateway & external OIDC
 *
 * Critical paths covered:
 * - Verify the external keycloak IdP configuration form renders correctly and saves
 * - Verify the form for manual OIDC endpoint entry when auto-discovery is disabled
 * - Verify validation errors when required endpoints are missing with auto-discovery disabled
 * - Verify that all configured OIDC providers are listed on the login page.
 * - Verify login page behavior after the built-in admin account is disabled with OIDC configured.
 *
 * Login form validation tests use raw `page` (not the `app` fixture) because `app`
 * auto-logs-in via the mock API. We intercept `/auth/refresh` to block
 * the bootstrap.
 */
import { test, expect, toAppUrl } from './fixtures'
import { AAP_AUTH_PROVIDER, KEYCLOAK_AUTH_PROVIDER, KEYCLOAK_OIDC_IDP } from './fixtures/mock-oidc-idps'
import { APP_TITLE } from './helpers/appTitle'
import { goToLoginPage } from './helpers/login'

test.describe('IdP configuration — keycloak external OIDC', () => {
  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/authentication'))
    await expect(app.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()

    await app.getByRole('link', { name: /Add OIDC provider/i }).click()
    await expect(app.getByRole('heading', { level: 1, name: 'Add OIDC provider' })).toBeVisible()

    await app.getByRole('button', { name: /Select a provider template/i }).click()
    const providerTemplateListbox = app.getByRole('listbox')
    await expect(providerTemplateListbox).toBeVisible()
    await expect(providerTemplateListbox.getByRole('option', { name: /Custom/i })).toBeVisible()
    await providerTemplateListbox.getByRole('option', { name: /Custom/i }).click()

    await app.getByRole('textbox', { name: /Provider name/i }).fill('Keycloak')

    const enabledToggle = app.getByRole('switch', { name: /Enabled/ })
    await expect(enabledToggle).toBeVisible()

    // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
    await enabledToggle.click({ force: true })

    await app.getByRole('textbox', { name: /Issuer URL/i }).fill('https://keycloak-service.example.com')
    await app.getByRole('textbox', { name: /Client ID/i }).fill('mock-client-id')
    await app.getByRole('textbox', { name: /Client secret/i }).fill('mock-client-secret')
  })

  test('Verify the external keycloak IdP configuration form renders correctly and saves', async ({ app }) => {
    await expect(app).toHaveTitle(`Add OIDC provider | Identity Providers | ${APP_TITLE}`)
    const autoDiscoveryToggle = app.getByRole('switch', { name: /Use OIDC Discovery/ })
    await expect(autoDiscoveryToggle).toBeVisible()
    await expect(autoDiscoveryToggle).toBeChecked()

    await app.route('**/api/v1/identity_providers**', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(KEYCLOAK_OIDC_IDP),
        })
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ resources: [KEYCLOAK_OIDC_IDP] }),
      })
    })

    await app.getByRole('button', { name: /Claim mapping/i }).click()
    await app.getByRole('button', { name: /Add provider/i }).click()
    await expect(app.getByRole('heading', { name: /Identity provider created/i })).toBeVisible()

    await expect(app.getByRole('row', { name: /Keycloak/i })).toBeVisible()
  })

  test('Verify the form for manual OIDC endpoint entry when auto-discovery is disabled', async ({ app }) => {
    const autoDiscoveryToggle = app.getByRole('switch', { name: /Use OIDC Discovery/ })
    await expect(autoDiscoveryToggle).toBeVisible()

    // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
    await autoDiscoveryToggle.click({ force: true })
    await expect(autoDiscoveryToggle).not.toBeChecked()

    await app
      .getByRole('textbox', { name: /Authorization endpoint/i })
      .fill('https://keycloak-service.example.com/oauth2/authorize')
    await app
      .getByRole('textbox', { name: /Token endpoint/i })
      .fill('https://keycloak-service.example.com/oauth2/token')
    await app.getByRole('textbox', { name: /JWKS URI/i }).fill('https://keycloak-service.example.com/oauth2/keys')

    const KEYCLOAK_OIDC_IDP_MANUAL = {
      ...KEYCLOAK_OIDC_IDP,
      configuration: {
        ...KEYCLOAK_OIDC_IDP.configuration,
        auto_discovery: false,
        authorization_endpoint: 'https://keycloak-service.example.com/oauth2/authorize',
        token_endpoint: 'https://keycloak-service.example.com/oauth2/token',
        jwks_uri: 'https://keycloak-service.example.com/oauth2/keys',
      },
    }

    await app.route('**/api/v1/identity_providers**', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(KEYCLOAK_OIDC_IDP_MANUAL),
        })
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ resources: [KEYCLOAK_OIDC_IDP_MANUAL] }),
      })
    })

    await app.getByRole('button', { name: /Claim mapping/i }).click()
    await app.getByRole('button', { name: /Add provider/i }).click()
    await expect(app.getByRole('heading', { name: /Identity provider created/i })).toBeVisible()

    await expect(app.getByRole('row', { name: /Keycloak/i })).toBeVisible()
  })

  test('Verify validation errors when required endpoints are missing with auto-discovery disabled', async ({ app }) => {
    const autoDiscoveryToggle = app.getByRole('switch', { name: /Use OIDC Discovery/ })
    await expect(autoDiscoveryToggle).toBeVisible()

    // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
    await autoDiscoveryToggle.click({ force: true })
    await expect(autoDiscoveryToggle).not.toBeChecked()

    await app
      .getByRole('textbox', { name: /Authorization endpoint/i })
      .fill('https://keycloak-service.example.com/oauth2/authorize')
    await app.getByRole('textbox', { name: /JWKS URI/i }).fill('https://keycloak-service.example.com/oauth2/keys')

    await app.getByRole('button', { name: /Next/i }).click()

    await expect(app.getByRole('textbox', { name: /Token endpoint/i })).toHaveAttribute('aria-invalid', 'true')
    await expect(app.getByText('Required when auto-discovery is disabled')).toBeVisible()
  })

  test('Group mapping tab loads without errors after creating a provider', async ({ app }) => {
    await app.route('**/api/v1/identity_providers**', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(KEYCLOAK_OIDC_IDP),
        })
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          KEYCLOAK_OIDC_IDP.id === new URL(route.request().url()).pathname.split('/').pop()
            ? KEYCLOAK_OIDC_IDP
            : { resources: [KEYCLOAK_OIDC_IDP] }
        ),
      })
    })

    await app.getByRole('button', { name: /Claim mapping/i }).click()
    await app.getByRole('button', { name: /Add provider/i }).click()
    await expect(app.getByRole('heading', { name: /Identity provider created/i })).toBeVisible()

    await app.getByRole('link', { name: /Keycloak/i }).click()

    await expect(app.getByRole('heading', { level: 1, name: /Keycloak/i })).toBeVisible()

    const groupMappingTab = app.getByRole('tab', { name: /Group mapping/i })
    await expect(groupMappingTab).toBeVisible()
    await groupMappingTab.click()

    await expect(app.locator('text=Something went wrong')).not.toBeVisible()
    await expect(app.locator('text=crypto.randomUUID')).not.toBeVisible()
  })
})

test.describe('IdP login form verification - list OIDC providers', () => {
  test('Login page - OIDC providers listed', async ({ page }) => {
    await goToLoginPage(page, { providers: [AAP_AUTH_PROVIDER, KEYCLOAK_AUTH_PROVIDER] })

    await expect(page.getByRole('button', { name: /Log in with AAP/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Log in with Keycloak/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Sign in using local account/i })).toBeVisible()
  })
})
