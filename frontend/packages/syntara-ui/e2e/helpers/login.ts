import { expect, appBaseUrl, type Page } from '../fixtures'

import { APP_TITLE } from './appTitle'

type AuthProviderFixture = {
  id: string
  name: string
  provider_type?: string
  provider_template?: string | null
}

type GoToLoginPageOptions = {
  providers?: AuthProviderFixture[]
  authError?: string
}

/**
 * Navigate to the login page in a clean state by blocking the bootstrap
 * refresh (which would auto-authenticate via cookie) and configuring
 * the providers response.
 *
 * @param providers - OIDC providers to display (empty → local-only login)
 * @param authError - Optional `auth_error` query param (simulates OIDC callback redirect)
 */
export async function goToLoginPage(page: Page, options: GoToLoginPageOptions = {}): Promise<void> {
  const { providers = [], authError } = options

  await page.route('**/api/v1/auth/csrf_token', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ csrf_token: 'mock-csrf-e2e' }),
    })
  )

  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({
        type: 'https://api.example.com/errors/unauthorized',
        title: 'Unauthorized',
        detail: 'Authentication required',
        code: 'AUTHENTICATION_REQUIRED',
      }),
    })
  )

  await page.route('**/api/v1/auth/providers', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ resources: providers }),
    })
  )

  const url = authError ? `${appBaseUrl}?auth_error=${authError}` : appBaseUrl
  await page.goto(url)
  await expect(page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })).toBeVisible()
}
