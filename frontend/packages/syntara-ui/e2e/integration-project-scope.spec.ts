/**
 * Integration project scope — design-time selector visibility.
 *
 * Verifies that integrations scoped to a project are visible only within
 * that project's workflow builder tool selector, and that integrations
 * scoped to other projects are excluded.
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, clickAddConnectedStep } from './helpers/workflows'
import {
  assignIntegrationProjectViaApi,
  createIntegrationViaApi,
  deleteIntegrationViaApi,
  patchIntegrationScopeViaApi,
  type SeededIntegration,
} from './seeds/resources'
import { apiRequest, ensureProject, getAuthToken } from './utils/api'

/**
 * Navigate to a fresh workflow builder, select a project by name,
 * add a manual trigger, then add a Task Agent node and open the
 * tool selector dropdown. Returns the tool options listbox locator.
 */
async function openAgentToolSelector(app: Page, projectName: string) {
  await app.goto(toAppUrl('/workflow-builder/new'))
  await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  const projectToggle = app.getByPlaceholder(/All projects|Select a project/)
  await projectToggle.click()
  await app.getByRole('option', { name: projectName }).click()

  await app.getByRole('button', { name: 'Manual trigger' }).click()
  await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await app.getByRole('button', { name: 'Create', exact: true }).click()

  const panel = await clickAddConnectedStep(app)
  await panel.getByRole('button', { name: 'Task Agent' }).click()

  const toolsInput = app.getByRole('textbox', { name: 'Select tools' })
  await expect(toolsInput).toBeVisible({ timeout: 15_000 })
  await toolsInput.click()

  const toolOptions = app.getByRole('listbox', { name: 'Tool options' })
  await expect(toolOptions).toBeVisible({ timeout: 10_000 })
  return toolOptions
}

test.describe('Integration project scope — selector visibility', () => {
  let projectScopedIntegration: SeededIntegration | null = null
  let globalIntegration: SeededIntegration | null = null
  let projectAId: string | null = null
  let projectAName: string | null = null
  let projectBId: string | null = null
  let projectBName: string | null = null
  let token: string | null = null

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      token = await getAuthToken(page)
      if (!token) return

      projectAName = buildUniqueName('e2e-scope-projA')
      const projectA = await ensureProject(page, projectAName)
      projectAId = projectA?.id ?? null

      projectBName = buildUniqueName('e2e-scope-projB')
      const projectB = await ensureProject(page, projectBName)
      projectBId = projectB?.id ?? null

      if (!projectAId || !projectBId) return

      globalIntegration = await createIntegrationViaApi(page, {
        name: buildUniqueName('e2e-scope-global'),
        token,
        discoveredTools: [{ name: 'global_tool', enabled: true }],
      })

      projectScopedIntegration = await createIntegrationViaApi(page, {
        name: buildUniqueName('e2e-scope-projA'),
        token,
        discoveredTools: [{ name: 'scoped_tool', enabled: true }],
      })
      if (projectScopedIntegration) {
        const patched = await patchIntegrationScopeViaApi(page, projectScopedIntegration.id, 'project', token)
        const assigned =
          patched &&
          projectAId &&
          (await assignIntegrationProjectViaApi(page, projectScopedIntegration.id, projectAId, token))
        if (!assigned) projectScopedIntegration = null
      }
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    try {
      if (projectScopedIntegration) await deleteIntegrationViaApi(page, projectScopedIntegration.id)
      if (globalIntegration) await deleteIntegrationViaApi(page, globalIntegration.id)
      const t = await getAuthToken(page)
      if (t) {
        if (projectAId) await apiRequest(page, 'delete', `/projects/${projectAId}`, { token: t })
        if (projectBId) await apiRequest(page, 'delete', `/projects/${projectBId}`, { token: t })
      }
    } finally {
      await page.close()
    }
  })

  test('assigned project tool selector shows both global and project-scoped integrations', async ({ app }) => {
    expect(globalIntegration && projectScopedIntegration && projectAName, 'Seed data not created').toBeTruthy()

    const toolOptions = await openAgentToolSelector(app, projectAName!)

    await expect(toolOptions.getByText(globalIntegration!.name)).toBeVisible()
    await expect(toolOptions.getByText(projectScopedIntegration!.name)).toBeVisible()
  })

  test('unassigned project tool selector shows only global integration', async ({ app }) => {
    expect(globalIntegration && projectScopedIntegration && projectBName, 'Seed data not created').toBeTruthy()

    const toolOptions = await openAgentToolSelector(app, projectBName!)

    await expect(toolOptions.getByText(globalIntegration!.name)).toBeVisible()
    await expect(toolOptions.getByText(projectScopedIntegration!.name)).not.toBeVisible()
  })
})
