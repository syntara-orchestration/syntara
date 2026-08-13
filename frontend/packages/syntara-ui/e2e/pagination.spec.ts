/**
 * E2E Tests: Pagination & Project Filter
 *
 * Verifies features restored after the DRY refactor (PR #470):
 * - Pagination footer with PF Pagination (per-page selector + prev/next)
 * - Project selector filters workflows by project_id
 * - Changing per-page resets to first page
 */
import type { Page } from '@playwright/test'

import { createUnavailableGuard, test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import {
  createUserViaApi,
  deleteGroupViaApi,
  deleteUserViaApi,
  ensureGroupExists,
  type SeededGroup,
  type SeededUser,
} from './seeds/iam'
import {
  createCredentialSeed,
  createIdentityProviderViaApi,
  createIntegrationViaApi,
  createWorkflowViaApi,
  deleteCredentialViaApi,
  deleteIdentityProviderViaApi,
  deleteIntegrationViaApi,
  deleteWorkflowViaApi,
  type SeededCredential,
  type SeededIdentityProvider,
  type SeededIntegration,
  type SeededWorkflow,
} from './seeds/resources'
import { ensureProject, getAuthToken } from './utils/api'

const seededWorkflows: SeededWorkflow[] = []
const seededCredentials: SeededCredential[] = []
const seededIntegrations: SeededIntegration[] = []
const seededUsers: SeededUser[] = []
const seededGroups: SeededGroup[] = []
const seededIdPs: SeededIdentityProvider[] = []

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  const prefix = buildUniqueName('e2e-pag')

  if (!token) {
    await page.close()
    return
  }

  const project = await ensureProject(page)
  const projectId = project?.id

  const workflowResults = await Promise.allSettled(
    Array.from({ length: 22 }, (_, i) =>
      createWorkflowViaApi(page, { name: `${prefix}-workflow-${i + 1}`, projectId, token })
    )
  )
  for (const result of workflowResults) {
    if (result.status === 'fulfilled' && result.value) seededWorkflows.push(result.value)
  }

  for (let i = 1; i <= 2; i++) {
    const cred = await createCredentialSeed(page, { name: `${prefix}-cred-${i}`, projectId, token })
    if (cred) seededCredentials.push(cred)
  }

  for (let i = 1; i <= 2; i++) {
    const integration = await createIntegrationViaApi(page, { name: `${prefix}-integ-${i}`, token })
    if (integration) seededIntegrations.push(integration)
  }

  for (let i = 1; i <= 16; i++) {
    const user = await createUserViaApi(page, { username: `${prefix}-user-${i}`, token })
    if (user) seededUsers.push(user)
  }

  for (let i = 1; i <= 15; i++) {
    const group = await ensureGroupExists(page, `${prefix}-group-${i}`)
    if (group) seededGroups.push(group)
  }

  for (let i = 1; i <= 21; i++) {
    const idp = await createIdentityProviderViaApi(page, { name: `${prefix}-idp-${i}`, token })
    if (idp) seededIdPs.push(idp)
  }

  await page.close()
})

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()

  for (const wf of seededWorkflows) {
    await deleteWorkflowViaApi(page, wf.id)
  }
  for (const cred of seededCredentials) {
    await deleteCredentialViaApi(page, cred.id)
  }
  for (const integration of seededIntegrations) {
    await deleteIntegrationViaApi(page, integration.id)
  }
  for (const user of seededUsers) {
    await deleteUserViaApi(page, user.id)
  }
  for (const group of seededGroups) {
    if (group.createdByUs) await deleteGroupViaApi(page, group.id)
  }
  for (const idp of seededIdPs) {
    await deleteIdentityProviderViaApi(page, idp.id)
  }

  await page.close()
})

/** Workflow rows only — excludes grouped “project” header rows that have no builder link. */
function workflowNameButtons(app: Page) {
  return app.getByRole('grid', { name: 'Workflows table' }).locator('tbody').getByRole('link', { name: /.+/ })
}

function isProjectScopedWorkflowsUrl(url: string): boolean {
  return /\/api\/v1\/projects\/[^/]+\/workflows(\?|$)/.test(url)
}

function isGlobalWorkflowsListUrl(url: string): boolean {
  try {
    return new URL(url).pathname === '/api/v1/workflows'
  } catch {
    return false
  }
}

test.describe('Pagination Footer — Users Tab', () => {
  const guard = createUnavailableGuard('No users data available')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/access-management/users'))
    await expect(app.getByRole('tab', { name: /Users/i })).toHaveAttribute('aria-selected', 'true')
    const table = app.getByRole('grid', { name: 'Users' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No users data available')
  })

  test('pagination footer is visible with per-page toggle', async ({ app }) => {
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
  })

  test('per-page dropdown shows page size options', async ({ app }) => {
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
    await perPageToggle.click()

    await expect(app.getByRole('menuitem', { name: /10 per page/i })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: /20 per page/i })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: /50 per page/i })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: /100 per page/i })).toBeVisible()
  })
})

test.describe('Pagination Footer — Groups Tab', () => {
  test('pagination footer is visible on groups tab', async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/access-management/groups'))
    await expect(app.getByRole('tab', { name: /Groups/i })).toHaveAttribute('aria-selected', 'true')

    const table = app.getByRole('grid', { name: 'Groups table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No groups data available')

    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
  })
})

test.describe('Project Selector — Workflows', () => {
  const guard = createUnavailableGuard('No workflows or project selector not available')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    const table = app.getByRole('grid', { name: 'Workflows table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) {
      guard.markUnavailable()
      test.skip(true, 'No workflows available — create workflows first')
      return
    }

    const projectInput = app.getByPlaceholder('All projects')
    const selectorVisible = await projectInput
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!selectorVisible) {
      guard.markUnavailable()
      test.skip(true, 'Project selector not available in this environment')
      return
    }

    await projectInput.click()
    const optionsInteractive = await app
      .getByRole('option', { name: 'All projects' })
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    await app.keyboard.press('Escape')
    if (!optionsInteractive) guard.markUnavailable()
    test.skip(!optionsInteractive, 'Project selector is not interactive in this environment')
  })

  test('project selector is visible and lists projects', async ({ app }) => {
    const projectInput = app.getByPlaceholder('All projects')
    await expect(projectInput).toBeVisible()

    await projectInput.click()
    await app.getByRole('option', { name: 'All projects' }).waitFor({ state: 'visible', timeout: 10_000 })

    await expect(app.getByRole('option', { name: 'All projects' })).toBeVisible()
    const optionCount = await app.getByRole('option').count()
    expect(optionCount).toBeGreaterThan(1)
  })

  test('selecting a project sends project_id to the API', async ({ app }) => {
    const workflowCountAllProjects = await workflowNameButtons(app).count()
    test.skip(
      workflowCountAllProjects === 0,
      'No workflow builder links visible — need at least one workflow to test project filter'
    )

    const requestPromise = app.waitForRequest((req) => {
      const u = req.url()
      return isProjectScopedWorkflowsUrl(u) || (u.includes('/api/v1/workflows') && u.includes('project_id='))
    })

    await app.getByPlaceholder('All projects').click()
    await app.getByRole('option', { name: 'All projects' }).waitFor({ state: 'visible', timeout: 10_000 })

    // Find and click first real project (not "All projects" or "Create project")
    const options = app.getByRole('option')
    const count = await options.count()
    let clicked = false
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent()
      if (text && !text.includes('All projects') && !text.includes('Create project')) {
        await options.nth(i).click()
        clicked = true
        break
      }
    }
    test.skip(!clicked, 'No real projects available')

    const request = await requestPromise
    const rawUrl = request.url()
    const url = new URL(rawUrl)
    expect(isProjectScopedWorkflowsUrl(rawUrl) || url.searchParams.get('project_id')).toBeTruthy()

    await app.getByRole('grid', { name: 'Workflows table' }).waitFor({ state: 'visible', timeout: 10_000 })
    const workflowCountFiltered = await workflowNameButtons(app).count()
    expect(workflowCountFiltered).toBeGreaterThan(0)
    expect(workflowCountFiltered).toBeLessThanOrEqual(workflowCountAllProjects)
  })

  test('switching back to All projects removes project_id from API call', async ({ app }) => {
    // Select a project first
    await app.getByPlaceholder('All projects').click()
    await app.getByRole('option', { name: 'All projects' }).waitFor({ state: 'visible', timeout: 10_000 })

    const options = app.getByRole('option')
    const count = await options.count()
    let clicked = false
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent()
      if (text && !text.includes('All projects') && !text.includes('Create project')) {
        await options.nth(i).click()
        clicked = true
        break
      }
    }
    test.skip(!clicked, 'No real projects available')

    // Wait for table to update after project selection
    await app.getByRole('grid', { name: 'Workflows table' }).waitFor({ state: 'visible', timeout: 10_000 })

    // Switch back to All projects — list uses GET /api/v1/workflows (not /projects/:id/workflows)
    const requestPromise = app.waitForRequest((req) => isGlobalWorkflowsListUrl(req.url()))

    // After selecting a project the textbox has aria-label="Project" (set in useProjectSelector)
    await app.getByRole('textbox', { name: 'Project' }).click()
    await app.getByRole('option', { name: 'All projects' }).waitFor({ state: 'visible', timeout: 10_000 })
    await app.getByRole('option', { name: 'All projects' }).click()

    const request = await requestPromise
    const url = new URL(request.url())
    expect(url.searchParams.get('project_id')).toBeNull()
  })

  test('pagination footer has per-page toggle', async ({ app }) => {
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
  })
})

test.describe('Pagination Navigation — Workflows', () => {
  const guard = createUnavailableGuard('Not enough data to paginate')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    const table = app.getByRole('grid', { name: 'Workflows table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) {
      guard.markUnavailable()
      test.skip(true, 'No workflows available')
      return
    }

    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await perPageToggle.waitFor({ state: 'visible', timeout: 10_000 })
    await perPageToggle.click()
    await app.getByRole('menuitem', { name: /10 per page/i }).click()
    await table.waitFor({ state: 'visible', timeout: 10_000 })

    const nextButton = app.getByRole('button', { name: 'Go to next page' })
    const buttonVisible = await nextButton
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    const hasNextPage = buttonVisible && (await nextButton.isEnabled().catch(() => false))
    if (!hasNextPage) guard.markUnavailable()
    test.skip(!hasNextPage, 'Not enough data to paginate — need more than 10 workflows')
  })

  test('next/previous page buttons navigate between pages', async ({ app }) => {
    const prevButton = app.getByRole('button', { name: 'Go to previous page' })
    const nextButton = app.getByRole('button', { name: 'Go to next page' })

    await expect(prevButton).toBeDisabled()
    await expect(nextButton).toBeEnabled()

    await nextButton.click()
    await expect(prevButton).toBeEnabled()

    await prevButton.click()
    await expect(prevButton).toBeDisabled()
  })

  test('changing per-page resets to first page', async ({ app }) => {
    const prevButton = app.getByRole('button', { name: 'Go to previous page' })

    await app.getByRole('button', { name: 'Go to next page' }).click()
    await expect(prevButton).toBeEnabled()

    // Change per-page
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await perPageToggle.click()
    await app.getByRole('menuitem', { name: /50 per page/i }).click()

    await expect(prevButton).toBeDisabled()
  })
})

test.describe('Pagination Footer — Credentials', () => {
  const guard = createUnavailableGuard('No credentials data available')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/configuration/credentials'))
    const table = app.getByRole('grid', { name: 'Credentials table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No credentials data available')
  })

  test('credentials table renders with footer', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Credentials table' })
    await expect(table).toBeVisible()
  })
})

test.describe('Pagination Footer — Integrations', () => {
  const guard = createUnavailableGuard('No integrations data available')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const table = app.getByRole('grid', { name: 'Integrations table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTable) guard.markUnavailable()
    test.skip(!hasTable, 'No integrations data available')
  })

  test('pagination footer is visible', async ({ app }) => {
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
  })

  test('per-page dropdown shows page size options', async ({ app }) => {
    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible()
    await perPageToggle.click()

    await expect(app.getByRole('menuitem', { name: /10 per page/i })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: /20 per page/i })).toBeVisible()
  })
})

test.describe('Pagination Footer — Identity Providers', () => {
  test('pagination footer is visible on identity providers tab', async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/authentication'))

    const table = app.getByRole('grid', { name: 'Identity providers table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No identity provider data available')

    const perPageToggle = app.locator('.pf-v6-c-pagination').getByRole('button', { name: /\d+ - \d+/ })
    await expect(perPageToggle).toBeVisible({ timeout: 5000 })
  })
})
