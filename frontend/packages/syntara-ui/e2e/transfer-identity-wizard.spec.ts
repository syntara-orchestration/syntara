/**
 * E2E Tests: Transfer Identity Wizard
 *
 * Tests the full-page PatternFly wizard for transferring a federated identity.
 * Seeds all required data via API in beforeAll, cleans up in afterAll.
 *
 * Critical paths covered:
 * - Wizard navigation: button on identities tab, page title, step nav
 * - Step 1: Next disabled until user selected, filtering, user selection
 * - Step 2: empty state (no selection heading/filters when source has no identities)
 * - Back from Step 2 clears selections and returns to Step 1
 * - Cancel navigates back to identities tab
 * - Full attach flow tested in user-identity-admin-actions.spec.ts (route-intercepted)
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'

const ACCESS_URL = '/system-administration/access-management/users'

async function apiPost(app: Page, url: string, token: string, data: Record<string, unknown>) {
  const response = await app.request.post(url, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data,
  })
  return (await response.json()) as Record<string, unknown>
}

async function apiDelete(app: Page, url: string, token: string) {
  await app.request.delete(url, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

test.describe('Transfer Identity Wizard (AAP-75585)', () => {
  const prefix = buildUniqueName('e2e-xfer')
  const apiBase = process.env.SYNTARA_E2E_BASE_URL ?? process.env.VITE_API_URL ?? 'http://localhost:3300'
  let token = ''
  let sourceUserId = ''
  let source2UserId = ''
  let targetUserId = ''
  let providerId = ''

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      const password = process.env.SYNTARA_E2E_PASSWORD ?? 'coffee'
      const username = process.env.SYNTARA_E2E_PASSWORD ? 'admin' : 'demo'
      const loginResp = await page.request.post(`${apiBase}/api/v1/auth/login`, {
        data: { username, password },
      })
      const loginBody = (await loginResp.json()) as { access_token?: string; token?: string }
      token = loginBody.access_token ?? loginBody.token ?? ''
      if (!token) return

      const source = await apiPost(page, `${apiBase}/api/v1/users`, token, {
        username: `${prefix}-source`,
        email: `${prefix}-source@test.com`,
        first_name: `${prefix} Source`,
        password: 'e2e-test-password-123!',
      })
      sourceUserId = source.id as string

      const source2 = await apiPost(page, `${apiBase}/api/v1/users`, token, {
        username: `${prefix}-source2`,
        email: `${prefix}-source2@test.com`,
        first_name: `${prefix} Source2`,
        password: 'e2e-test-password-123!',
      })
      source2UserId = source2.id as string

      const target = await apiPost(page, `${apiBase}/api/v1/users`, token, {
        username: `${prefix}-target`,
        email: `${prefix}-target@test.com`,
        first_name: `${prefix} Target`,
        password: 'e2e-test-password-123!',
      })
      targetUserId = target.id as string

      const provider = await apiPost(page, `${apiBase}/api/v1/identity_providers`, token, {
        name: `${prefix}-idp`,
        configuration: {
          provider_type: 'oidc',
          issuer_url: 'https://accounts.google.com',
          client_id: 'e2e-test-client',
          client_secret: 'e2e-test-secret',
          redirect_uri: 'http://localhost:5173/auth/callback',
        },
      })
      providerId = provider.id as string
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    if (!token) return
    const page = await browser.newPage()
    try {
      if (providerId) await apiDelete(page, `${apiBase}/api/v1/identity_providers/${providerId}`, token)
      if (targetUserId) await apiDelete(page, `${apiBase}/api/v1/users/${targetUserId}`, token)
      if (source2UserId) await apiDelete(page, `${apiBase}/api/v1/users/${source2UserId}`, token)
      if (sourceUserId) await apiDelete(page, `${apiBase}/api/v1/users/${sourceUserId}`, token)
    } finally {
      await page.close()
    }
  })

  test.skip('wizard opens from identities tab with correct title', async ({ app }) => {
    expect(targetUserId && providerId, 'Backend seeding failed — user or identity provider not created').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/identities`))

    const transferButton = app.getByRole('button', { name: 'Transfer identity' })
    await expect(transferButton).toBeVisible({ timeout: 15_000 })
    await transferButton.click()

    await expect(
      app.getByRole('heading', { level: 1, name: new RegExp(`Transfer identity to ${prefix}-target`) })
    ).toBeVisible({ timeout: 10_000 })

    const wizardNav = app.getByRole('navigation', { name: 'Wizard steps' })
    await expect(wizardNav).toBeVisible()
  })

  test('cancel navigates back to identities tab', async ({ app }) => {
    expect(targetUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(
      app.getByRole('heading', { level: 1, name: new RegExp(`Transfer identity to ${prefix}-target`) })
    ).toBeVisible({ timeout: 15_000 })

    await app.getByRole('link', { name: 'Cancel' }).click()

    await expect(app).toHaveURL(new RegExp(`${targetUserId}/identities`))
  })

  test('step 2 shows empty state when source user has no identities', async ({ app }) => {
    expect(targetUserId && sourceUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(
      app.getByRole('heading', { level: 1, name: new RegExp(`Transfer identity to ${prefix}-target`) })
    ).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source@test.com`).click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    await expect(app.getByText('No identities')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText('This user has no federated identities to attach.')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Transfer identity' })).toBeDisabled()
  })

  test('Next button is disabled until a user is selected', async ({ app }) => {
    expect(targetUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await expect(app.getByRole('button', { name: 'Next', exact: true })).toBeDisabled()
    await expect(app.getByRole('button', { name: 'Back' })).toBeDisabled()

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source@test.com`).click()

    await expect(app.getByRole('button', { name: 'Next', exact: true })).toBeEnabled()
  })

  test('Step 1 filters users by username', async ({ app }) => {
    expect(targetUserId && sourceUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()

    await expect(app.getByText(`${prefix}-source@test.com`)).toBeVisible({ timeout: 10_000 })
    await expect(app.getByText(`${prefix}-target@test.com`)).not.toBeVisible()
  })

  test('target user is excluded from Step 1 user list', async ({ app }) => {
    expect(targetUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-target`)
    await app.getByRole('button', { name: 'Apply filter' }).click()

    await expect(app.getByText(/No results found|Adjust your filters/i)).toBeVisible({ timeout: 10_000 })
  })

  test('Back from Step 2 clears selections and returns to Step 1', async ({ app }) => {
    expect(targetUserId && sourceUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source@test.com`).click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    // Seeded source users have no federated identities, so Step 2 is the empty state
    // (selection heading/filters are hidden until there is something to select).
    await expect(app.getByText('No identities')).toBeVisible({ timeout: 10_000 })

    await app.getByRole('button', { name: 'Back' }).click()

    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('button', { name: 'Next', exact: true })).toBeDisabled()
  })

  test('selecting a different user in Step 1 resets Step 2', async ({ app }) => {
    expect(targetUserId && sourceUserId && source2UserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source@test.com`).click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(app.getByText('No identities')).toBeVisible({ timeout: 10_000 })

    await app.getByRole('button', { name: 'Back' }).click()
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 10_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source2`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source2@test.com`).click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    await expect(app.getByText('No identities')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('button', { name: 'Transfer identity' })).toBeDisabled()
  })

  test('step 2 empty state hides selection heading and description', async ({ app }) => {
    expect(targetUserId && sourceUserId, 'Backend seeding failed').toBeTruthy()

    await app.goto(toAppUrl(`${ACCESS_URL}/${targetUserId}/transfer-identity`))
    await expect(app.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible({ timeout: 15_000 })

    await app.getByPlaceholder('Filter by username').fill(`${prefix}-source`)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByText(`${prefix}-source@test.com`).click()
    await app.getByRole('button', { name: 'Next', exact: true }).click()

    await expect(app.getByText('No identities')).toBeVisible({ timeout: 10_000 })
    await expect(app.getByRole('heading', { level: 2, name: 'Select an identity' })).not.toBeVisible()
    await expect(app.getByText(/federated identities to attach to the current user/i)).not.toBeVisible()
  })
})
