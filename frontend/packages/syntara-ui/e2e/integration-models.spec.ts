/**
 * E2E Tests: LLM Provider Models Tab
 *
 * Critical paths covered:
 * - Navigate to models tab from integrations list
 * - Toggle individual models (enable/disable via checkboxes) and save
 * - Select all / deselect all models
 * - Set a model as default via kebab menu
 * - Remove default model via kebab menu
 * - Filter models by name
 * - Save model changes and verify persistence on revisit
 * - Allow-list changes propagate to the Agent node model selector (Test 15)
 *
 * Edge cases:
 * - Filter with no results shows empty filter state
 * - Clear filter restores full list
 */
import { type Page } from '@playwright/test'

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, clickAddConnectedStep, startWorkflowWithTrigger } from './helpers/workflows'
import { deleteIntegrationViaApi, type SeededIntegration } from './seeds/resources'
import { apiRequest, deleteCredentialViaApi, ensureProject } from './utils/api'

async function ensureLlmCredentialId(app: Page): Promise<string> {
  const project = await ensureProject(app)
  if (!project) throw new Error('Could not ensure project for credential creation')

  const typesResp = await apiRequest(app, 'get', '/credential_types')
  if (!typesResp.ok()) throw new Error('Could not list credential types')
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  const llmType = types.resources?.find((t) => t.name === 'LLM Provider')
  if (!llmType) throw new Error('LLM Provider credential type not found')

  const credName = `e2e-llm-models-cred-${Date.now()}`
  const createResp = await apiRequest(app, 'post', '/credentials', {
    data: {
      name: credName,
      credential_type_id: llmType.id,
      project_id: project.id,
      inputs: { api_key: 'sk-e2e-test-key' },
    },
  })
  if (!createResp.ok()) throw new Error('Could not create LLM credential')
  const cred = (await createResp.json()) as { id: string }
  return cred.id
}

type LLMIntegrationResult = SeededIntegration & { credentialId: string }

async function createLLMIntegration(app: Page, name: string): Promise<LLMIntegrationResult> {
  const credentialId = await ensureLlmCredentialId(app)

  const resp = await apiRequest(app, 'post', '/integrations', {
    data: {
      name,
      integration_type: 'llm_provider',
      configuration: {
        integration_type: 'llm_provider',
        provider_hint: 'custom',
        base_url: `https://example.com/v1`,
      },
      management_credential_id: credentialId,
      scope: 'global',
      discovered_models: [
        {
          model_id: 'model-alpha',
          name: 'Alpha Model',
          description: 'First test model',
          enabled: true,
          is_default: true,
        },
        {
          model_id: 'model-beta',
          name: 'Beta Model',
          description: 'Second test model',
          enabled: true,
          is_default: false,
        },
        {
          model_id: 'model-gamma',
          name: 'Gamma Model',
          description: 'Third test model',
          enabled: false,
          is_default: false,
        },
      ],
    },
  })
  if (!resp.ok()) {
    const text = await resp.text()
    throw new Error(`Failed to create LLM integration "${name}" via API: ${resp.status()} ${text}`)
  }
  const integration = (await resp.json()) as { id: string; name: string }
  return { id: integration.id, name: integration.name, credentialId }
}

async function navigateToModelsTab(app: Page, integrationName: string) {
  await app.goto(toAppUrl('/configuration/integrations'))
  await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
  await app.getByPlaceholder('Filter by name').fill(integrationName)
  await app.getByRole('button', { name: 'Apply filter' }).click()
  const row = app.getByRole('row', { name: new RegExp(integrationName) })
  await expect(row).toBeVisible()
  await row.getByRole('link', { name: integrationName, exact: true }).click()
  await app.getByRole('tab', { name: /Enabled resources/i }).click()
}

test.describe('LLM Provider Models Tab', () => {
  test('navigates to models tab and displays models', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-nav')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()
      await expect(app.getByRole('button', { name: 'Save model changes' })).toBeVisible()
      const checkboxes = modelsTable.getByRole('checkbox')
      const count = await checkboxes.count()
      expect(count).toBeGreaterThan(0)
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('toggles individual model enable/disable via checkbox', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-toggle')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const gammaRow = modelsTable.getByRole('row').filter({ hasText: 'Gamma Model' })
      const gammaCheckbox = gammaRow.getByRole('checkbox')

      await expect(gammaCheckbox).not.toBeChecked()
      await gammaCheckbox.click()
      await expect(gammaCheckbox).toBeChecked()

      await gammaCheckbox.click()
      await expect(gammaCheckbox).not.toBeChecked()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('select all and deselect all models', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-selall')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const selectAllCheckbox = modelsTable.locator('thead').getByRole('checkbox')
      await selectAllCheckbox.click()

      const bodyCheckboxes = modelsTable.locator('tbody').getByRole('checkbox')
      const count = await bodyCheckboxes.count()
      for (let i = 0; i < count; i++) {
        await expect(bodyCheckboxes.nth(i)).toBeChecked()
      }

      await selectAllCheckbox.click()

      for (let i = 0; i < count; i++) {
        await expect(bodyCheckboxes.nth(i)).not.toBeChecked()
      }
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('sets a model as default via kebab menu', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-default')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const betaRow = modelsTable.getByRole('row').filter({ hasText: 'Beta Model' })
      await betaRow.getByRole('button', { name: /Actions/i }).click()
      await app.getByRole('menuitem', { name: /Set as default model/i }).click()

      await expect(betaRow.getByText('Default')).toBeVisible()
      const alphaRow = modelsTable.getByRole('row').filter({ hasText: 'Alpha Model' })
      await expect(alphaRow.getByText('Default')).not.toBeVisible()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('removes default model via kebab menu', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-rmdefault')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const alphaRow = modelsTable.getByRole('row').filter({ hasText: 'Alpha Model' })
      await expect(alphaRow.getByText('Default')).toBeVisible()

      await alphaRow.getByRole('button', { name: /Actions/i }).click()
      await app.getByRole('menuitem', { name: /Remove default model/i }).click()

      await expect(alphaRow.getByText('Default')).not.toBeVisible()
      await expect(modelsTable.getByText('Default')).not.toBeVisible()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('saves model changes and verifies persistence on revisit @pr-check', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-save')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const gammaRow = modelsTable.getByRole('row').filter({ hasText: 'Gamma Model' })
      const gammaCheckbox = gammaRow.getByRole('checkbox')
      await expect(gammaCheckbox).not.toBeChecked()
      await gammaCheckbox.click()
      await expect(gammaCheckbox).toBeChecked()

      await app.getByRole('button', { name: 'Save model changes' }).click()
      await expect(app.getByText('Models updated')).toBeVisible()

      await navigateToModelsTab(app, name)

      const revisitTable = app.locator('[aria-label="Integration models"]')
      await expect(revisitTable).toBeVisible()

      const gammaRevisit = revisitTable.getByRole('row').filter({ hasText: 'Gamma Model' })
      await expect(gammaRevisit.getByRole('checkbox')).toBeChecked()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('filters models by name', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-filter')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      await app.getByPlaceholder('Filter by name').fill('Alpha')
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const visibleRows = modelsTable.locator('tbody tr')
      await expect(visibleRows).toHaveCount(1)
      await expect(visibleRows.nth(0)).toContainText('Alpha Model')
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('shows empty filter state when no models match', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-noresults')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      await expect(app.locator('[aria-label="Integration models"]')).toBeVisible()

      await app.getByPlaceholder('Filter by name').fill('nonexistent-xyz-model')
      await app.getByRole('button', { name: 'Apply filter' }).click()

      await expect(app.getByRole('heading', { name: /No results found/i })).toBeVisible()
      await expect(app.getByRole('button', { name: /Clear all filters/i }).last()).toBeVisible()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('clears filter and restores full list', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-clearfilter')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const initialRows = await modelsTable.locator('tbody tr').count()

      await app.getByPlaceholder('Filter by name').fill('Alpha')
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(modelsTable.locator('tbody tr')).toHaveCount(1)

      await app.getByRole('button', { name: /Clear all filters/i }).click()
      await expect(modelsTable.locator('tbody tr')).toHaveCount(initialRows)
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('allow-list and default changes propagate to agent node model selector', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-propagate')
    const integration = await createLLMIntegration(app, name)

    try {
      // 1. Open workflow builder, add an Agent node, verify initial model state
      await startWorkflowWithTrigger(app)

      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Task Agent' }).click()

      const modelToggle = app.getByRole('button', { name: 'Model', exact: true })
      await expect(modelToggle).toBeEnabled({ timeout: 10_000 })
      await modelToggle.click()

      // Scope assertions to this test's integration group to avoid collisions with parallel tests.
      // PatternFly SelectGroup renders a <section> containing the heading and its listbox.
      const modelGroup = app.locator('section').filter({ has: app.getByRole('heading', { name, level: 1 }) })

      // Only enabled models (Alpha, Beta) should be visible; Gamma (disabled) should not
      await expect(modelGroup.getByRole('option', { name: /Alpha Model/ })).toBeVisible({ timeout: 15_000 })
      await expect(modelGroup.getByRole('option', { name: /Beta Model/ })).toBeVisible()
      await expect(modelGroup.getByRole('option', { name: /Gamma Model/ })).not.toBeAttached()

      // Alpha is the default model — it should have the Default badge
      const alphaOption = modelGroup.getByRole('option', { name: /Alpha Model/ })
      await expect(alphaOption.getByText('Default')).toBeVisible()

      await app.keyboard.press('Escape')

      // Close the agent form without saving
      await app.getByRole('button', { name: 'Cancel step creation' }).click()

      // 2. Navigate to integration models tab and change the allow-list:
      //    - Disable Beta, enable Gamma, set Gamma as default
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      // Disable Beta (uncheck)
      const betaRow = modelsTable.getByRole('row').filter({ hasText: 'Beta Model' })
      await betaRow.getByRole('checkbox').click()
      await expect(betaRow.getByRole('checkbox')).not.toBeChecked()

      // Enable Gamma (check)
      const gammaRow = modelsTable.getByRole('row').filter({ hasText: 'Gamma Model' })
      await gammaRow.getByRole('checkbox').click()
      await expect(gammaRow.getByRole('checkbox')).toBeChecked()

      // Set Gamma as default (replacing Alpha)
      await gammaRow.getByRole('button', { name: /Actions/i }).click()
      await app.getByRole('menuitem', { name: /Set as default model/i }).click()
      await expect(gammaRow.getByText('Default')).toBeVisible()

      // Save
      await app.getByRole('button', { name: 'Save model changes' }).click()
      await expect(app.getByText('Models updated')).toBeVisible()

      // 3. Return to the workflow builder and verify allow-list changes are reflected
      await startWorkflowWithTrigger(app)

      const panel2 = await clickAddConnectedStep(app)
      await panel2.getByRole('button', { name: 'Task Agent' }).click()

      const modelToggle2 = app.getByRole('button', { name: 'Model', exact: true })
      await expect(modelToggle2).toBeEnabled({ timeout: 10_000 })
      await modelToggle2.click()

      // Scope to this test's integration group again
      const modelGroup2 = app.locator('section').filter({ has: app.getByRole('heading', { name, level: 1 }) })

      // Alpha (still enabled) and Gamma (now enabled) should be visible
      await expect(modelGroup2.getByRole('option', { name: /Alpha Model/ })).toBeVisible({ timeout: 15_000 })
      await expect(modelGroup2.getByRole('option', { name: /Gamma Model/ })).toBeVisible()

      // Beta (now disabled) should not appear
      await expect(modelGroup2.getByRole('option', { name: /Beta Model/ })).not.toBeAttached()

      // Gamma should now have the Default badge; Alpha should not
      const gammaOption = modelGroup2.getByRole('option', { name: /Gamma Model/ })
      await expect(gammaOption.getByText('Default')).toBeVisible()
      const alphaOption2 = modelGroup2.getByRole('option', { name: /Alpha Model/ })
      await expect(alphaOption2.getByText('Default')).not.toBeAttached()

      await app.keyboard.press('Escape')
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })

  test('shows error toast when save fails', async ({ app }) => {
    const name = buildUniqueName('e2e-llm-saveerr')
    const integration = await createLLMIntegration(app, name)

    try {
      await navigateToModelsTab(app, name)

      const modelsTable = app.locator('[aria-label="Integration models"]')
      await expect(modelsTable).toBeVisible()

      const gammaRow = modelsTable.getByRole('row').filter({ hasText: 'Gamma Model' })
      await gammaRow.getByRole('checkbox').click()

      await app.route('**/models/bulk_update', (route) =>
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        })
      )

      await app.getByRole('button', { name: 'Save model changes' }).click()
      await expect(app.getByText('Failed to update models')).toBeVisible()
    } finally {
      await deleteIntegrationViaApi(app, integration.id)
      await deleteCredentialViaApi(app, integration.credentialId)
    }
  })
})
