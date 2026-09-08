/**
 * E2E Tests: Service Accounts — List Page and Create Form
 *
 * Test cases from ANSTRAT-1972 test plan (AAP-79403):
 * - UI-1: List page columns and layout
 * - UI-2: List page empty state
 * - UI-3: Create form and one-time secret modal
 * - UI-4: Create form validation errors
 * - UI-13: Zero-role creation allowed
 */
import { type Page, test, expect, toAppUrl } from './fixtures'
import {
  createTestServiceAccount,
  deleteServiceAccountViaApi,
  filterServiceAccountByName,
  goToServiceAccountsList,
} from './helpers/service-accounts'
import { buildUniqueName } from './helpers/workflows'

const SERVICE_ACCOUNTS_URL = '/system-administration/access-management/service-accounts'

const MOCK_PROJECT_UUID = '00000000-0000-4000-8000-000000000001'
const MOCK_SA_ID = '00000000-0000-4000-8000-sa0000000001'
const MOCK_PROJECTS_RESPONSE = {
  resources: [
    {
      id: MOCK_PROJECT_UUID,
      name: 'default',
      description: 'Default project',
      is_default: true,
      is_builtin: false,
      labels: {},
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  ],
  next_cursor: null,
}

async function interceptCreateServiceAccountFlow(app: Page, saName: string) {
  await app.route(
    (url) => url.pathname === '/api/v1/projects',
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PROJECTS_RESPONSE),
      })
    }
  )

  await app.route(
    (url) => url.pathname === '/api/v1/service_accounts' && !url.pathname.includes('/credentials'),
    async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: MOCK_SA_ID,
            name: saName,
            description: null,
            status: 'active',
            project_id: MOCK_PROJECT_UUID,
            project_name: 'default',
            is_project_deleted: false,
            last_authenticated_at: null,
            created_by: 'u-001',
            updated_by: null,
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            labels: {},
          }),
        })
      } else {
        await route.fallback()
      }
    }
  )

  await app.route(
    (url) => url.pathname.includes('/credentials') && url.pathname.includes('/service_accounts/'),
    async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'cred-e2e-001',
            service_account_id: MOCK_SA_ID,
            credential_type: 'client_credentials',
            identifier: `nx_sa_${saName.replace(/-/g, '_')}_001`,
            client_secret: `nxs_mock_secret_${saName}_001`,
            status: 'active',
            grace_period_seconds: 3600,
            expires_at: null,
            last_used_at: null,
            created_by: 'u-001',
            updated_by: null,
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          }),
        })
      } else {
        await route.fallback()
      }
    }
  )
}

test.describe('UI-1: Service Accounts List Page — Columns and Layout', () => {
  let activeSA: { id: string; name: string }
  let disabledSA: { id: string; name: string }
  const prefix = buildUniqueName('sa-layout')

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      activeSA = await createTestServiceAccount(page, { prefix: `${prefix}-active` })
      disabledSA = await createTestServiceAccount(page, { prefix: `${prefix}-disabled`, disabled: true })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      await deleteServiceAccountViaApi(page, activeSA.id)
      await deleteServiceAccountViaApi(page, disabledSA.id)
    } finally {
      await page.close()
    }
  })

  test('displays required column headers', async ({ app }) => {
    await goToServiceAccountsList(app)

    await expect(app.getByRole('columnheader', { name: /name/i })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: /owning project/i })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: /created/i })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: /last authenticated/i })).toBeVisible()
    await expect(app.getByRole('columnheader', { name: /state/i })).toBeVisible()
  })

  test('shows active and disabled service accounts with correct status toggles', async ({ app }) => {
    await goToServiceAccountsList(app)
    await filterServiceAccountByName(app, prefix)

    const activeRow = app.getByRole('row', { name: new RegExp(activeSA.name) })
    await expect(activeRow).toBeVisible()
    await expect(activeRow.getByRole('switch')).toBeChecked()

    const disabledRow = app.getByRole('row', { name: new RegExp(disabledSA.name) })
    await expect(disabledRow).toBeVisible()
    await expect(disabledRow.getByRole('switch')).not.toBeChecked()
  })

  test('renders service account name as a link to the detail page', async ({ app }) => {
    await goToServiceAccountsList(app)
    await filterServiceAccountByName(app, prefix)

    const link = app.getByRole('link', { name: activeSA.name })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', new RegExp(activeSA.id))
  })

  test('shows owning project as a link', async ({ app }) => {
    await goToServiceAccountsList(app)
    await filterServiceAccountByName(app, prefix)

    const activeRow = app.getByRole('row', { name: new RegExp(activeSA.name) })
    const projectLink = activeRow.getByRole('link', { name: 'default' })
    await expect(projectLink).toBeVisible()
  })
})

test.describe('UI-2: Service Accounts List Page — Empty State', () => {
  let sa: { id: string; name: string }

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      sa = await createTestServiceAccount(page, { prefix: 'sa-empty-filter' })
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      await deleteServiceAccountViaApi(page, sa.id)
    } finally {
      await page.close()
    }
  })

  test('shows empty state when no service accounts match the filter', async ({ app }) => {
    await goToServiceAccountsList(app)

    const nonExistentName = buildUniqueName('sa-nonexistent')
    await filterServiceAccountByName(app, nonExistentName)

    await expect(app.getByText('No results found')).toBeVisible()
  })

  test('empty state shows create CTA when no service accounts exist', async ({ app }) => {
    await app.route('**/api/v1/service_accounts*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ resources: [], next_cursor: null }),
      })
    })

    await app.goto(toAppUrl(SERVICE_ACCOUNTS_URL))
    await expect(app.getByText('No service accounts yet')).toBeVisible()
    await expect(app.getByRole('button', { name: 'Create service account' })).toBeVisible()
  })
})

test.describe('UI-3: Create Service Account — Form and One-Time Secret Modal', () => {
  test('creates a service account and displays credentials in the reveal modal', async ({ app }) => {
    const saName = buildUniqueName('sa-create')

    await interceptCreateServiceAccountFlow(app, saName)
    await goToServiceAccountsList(app)
    await app.getByRole('button', { name: 'Create service account' }).click()

    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()

    // Verify form fields are present
    await expect(modal.getByRole('button', { name: 'Select a project' })).toBeVisible()
    await expect(modal.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await expect(modal.getByRole('textbox', { name: 'Description', exact: true })).toBeVisible()

    // Fill form: project first, then name and description
    // Project Select menu is portaled to document body (PatternFly default)
    await modal.getByRole('button', { name: 'Select a project' }).click()
    await app.getByRole('option', { name: 'default', exact: true }).click()

    await modal.getByRole('textbox', { name: 'Name', exact: true }).fill(saName)
    await modal.getByRole('textbox', { name: 'Description', exact: true }).fill('E2E test service account')

    // Submit
    await modal.getByRole('button', { name: 'Create service account' }).click()

    // Verify credentials reveal phase
    await expect(modal.getByText('Service account created')).toBeVisible({ timeout: 15_000 })

    await expect(modal.getByText('Save these credentials now')).toBeVisible()

    // Verify credential fields are present and contain non-empty values
    const credentialInputs = modal.getByRole('textbox')
    await expect(credentialInputs).toHaveCount(2)
    const [firstCredential, secondCredential] = await credentialInputs.all()
    expect((await firstCredential.inputValue()).length).toBeGreaterThan(0)
    expect((await secondCredential.inputValue()).length).toBeGreaterThan(0)

    // Verify buttons are disabled until acknowledgement — scope to <footer> to avoid matching modal X button
    const footer = modal.locator('footer')
    await expect(footer.getByRole('button', { name: 'Proceed to assignments' })).toBeDisabled()
    await expect(footer.getByRole('button', { name: 'Close' })).toBeDisabled()

    // Acknowledge and close
    await modal.getByLabel('I have saved the credentials').check()
    await expect(footer.getByRole('button', { name: 'Close' })).toBeEnabled()
    await footer.getByRole('button', { name: 'Close' }).click()
  })
})

test.describe('UI-4: Create Service Account — Validation Errors', () => {
  test('shows validation error when name is empty', async ({ app }) => {
    await goToServiceAccountsList(app)
    await app.getByRole('button', { name: 'Create service account' }).click()

    const modal = app.getByRole('dialog')

    // Select a project so only name is missing
    await modal.getByRole('button', { name: 'Select a project' }).click()
    await app.getByRole('option', { name: 'default', exact: true }).click()

    // Submit without filling name
    await modal.getByRole('button', { name: 'Create service account' }).click()

    await expect(modal.getByText('Name is required')).toBeVisible()

    // Cancel to clean up modal state
    await modal.getByRole('button', { name: 'Cancel' }).click()
  })

  test('shows validation error when project is not selected', async ({ app }) => {
    await goToServiceAccountsList(app)
    await app.getByRole('button', { name: 'Create service account' }).click()

    const modal = app.getByRole('dialog')

    // Fill name but don't select project
    await modal.getByRole('textbox', { name: 'Name', exact: true }).fill('valid-name')

    // Submit without selecting project
    await modal.getByRole('button', { name: 'Create service account' }).click()

    // The error text "Select a project" appears as helper text below the select (distinct from the button text)
    await expect(modal.getByText('Select a project')).toHaveCount(2)

    await modal.getByRole('button', { name: 'Cancel' }).click()
  })

  test('shows validation error for invalid name format', async ({ app }) => {
    await goToServiceAccountsList(app)
    await app.getByRole('button', { name: 'Create service account' }).click()

    const modal = app.getByRole('dialog')

    // Select project
    await modal.getByRole('button', { name: 'Select a project' }).click()
    await app.getByRole('option', { name: 'default', exact: true }).click()

    // Fill name with uppercase characters (invalid)
    await modal.getByRole('textbox', { name: 'Name', exact: true }).fill('Invalid-Name')

    // Submit
    await modal.getByRole('button', { name: 'Create service account' }).click()

    await expect(
      modal.getByText('Use lowercase letters, numbers, and hyphens only. Must start and end with a letter or number.')
    ).toBeVisible()

    await modal.getByRole('button', { name: 'Cancel' }).click()
  })
})

test.describe('UI-13: Create Service Account — Zero-Role Creation Allowed', () => {
  test('creates a service account without role assignments and shows empty assignments tab', async ({ app }) => {
    const saName = buildUniqueName('sa-no-roles')

    await interceptCreateServiceAccountFlow(app, saName)

    // Also intercept the detail page and assignments endpoints for navigation after creation
    await app.route(
      (url) => url.pathname === `/api/v1/service_accounts/${MOCK_SA_ID}`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: MOCK_SA_ID,
            name: saName,
            description: null,
            status: 'active',
            project_id: MOCK_PROJECT_UUID,
            project_name: 'default',
            is_project_deleted: false,
            last_authenticated_at: null,
            created_by: 'u-001',
            updated_by: null,
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            labels: {},
          }),
        })
      }
    )

    await app.route(
      (url) => url.pathname === '/api/v1/role_assignments',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ resources: [], next_cursor: null }),
        })
      }
    )

    await goToServiceAccountsList(app)
    await app.getByRole('button', { name: 'Create service account' }).click()

    const modal = app.getByRole('dialog')

    // Fill only required fields — no role assignment
    await modal.getByRole('button', { name: 'Select a project' }).click()
    await app.getByRole('option', { name: 'default', exact: true }).click()
    await modal.getByRole('textbox', { name: 'Name', exact: true }).fill(saName)

    // Submit
    await modal.getByRole('button', { name: 'Create service account' }).click()

    // Verify creation succeeded
    await expect(modal.getByText('Service account created')).toBeVisible({ timeout: 15_000 })

    // Acknowledge credentials and use "Proceed to assignments" to navigate to detail
    await modal.getByLabel('I have saved the credentials').check()
    await modal.getByRole('button', { name: 'Proceed to assignments' }).click()

    // Should be on the assignments tab of the detail page
    await expect(app).toHaveURL(/service-accounts\/.*\/assignments/)
    await expect(app.getByText('No role assignments')).toBeVisible()
  })
})
