/**
 * Helper functions for LLM model and credential selection in E2E tests.
 *
 * Covers the LLM model picker UX: selecting a model from the grouped
 * integration dropdown, then configuring a credential via "Set up connection".
 *
 * The model dropdown requires an enabled `llm_provider` integration with
 * discovered models. Use `createLlmIntegration()` before `selectLlmCredential()`.
 */

import { expect, type Page } from '../fixtures'
import { apiRequest, ensureProject } from '../utils/api'

/**
 * Determine the project the builder's CredentialSelector will filter by.
 *
 * For saved workflows (/workflow-builder/<id>), reads the workflow's project_id
 * from the API. For new workflows (/workflow-builder/new), falls back to the
 * first available project (matching what selectProjectIfRequired would pick).
 */
async function getBuilderProjectId(page: Page): Promise<string> {
  const wfIdMatch = page.url().match(/workflow-builder\/([^/?#]+)/)
  if (wfIdMatch && wfIdMatch[1] !== 'new') {
    const wfResp = await apiRequest(page, 'get', `/workflows/${wfIdMatch[1]}`)
    if (wfResp.ok()) {
      const wf = (await wfResp.json()) as { project_id?: string }
      if (wf.project_id) return wf.project_id
    }
  }

  const project = await ensureProject(page)
  if (!project) throw new Error('Could not determine builder project')
  return project.id
}

/**
 * Ensure an LLM Provider credential exists via the API.
 * Returns the credential name for selection in the UI dropdown.
 *
 * Creates the credential under the workflow's project so the
 * CredentialSelector (which filters by project_id) can find it.
 */
export async function ensureLlmCredential(page: Page): Promise<{ name: string; id: string }> {
  const targetProjectId = await getBuilderProjectId(page)
  const credName = 'e2e-llm-provider'

  // Check if it already exists under the target project
  const listResp = await apiRequest(page, 'get', `/credentials?name=${encodeURIComponent(credName)}`)
  if (listResp.ok()) {
    const body = (await listResp.json()) as { resources?: Array<{ id: string; name: string; project_id?: string }> }
    const match = body.resources?.find((c) => c.project_id === targetProjectId)
    if (match) return { name: credName, id: match.id }

    // Exists under wrong project — delete so we can recreate under the right one
    if (body.resources?.length) {
      await apiRequest(page, 'delete', `/credentials/${body.resources[0].id}`)
    }
  }

  // Find LLM Provider credential type
  const typesResp = await apiRequest(page, 'get', '/credential_types')
  if (!typesResp.ok()) throw new Error('Could not list credential types')
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  const llmType = types.resources?.find((t) => t.name === 'LLM Provider')
  if (!llmType) throw new Error('LLM Provider credential type not found')

  // Create the credential
  const createResp = await apiRequest(page, 'post', '/credentials', {
    data: {
      name: credName,
      credential_type_id: llmType.id,
      project_id: targetProjectId,
      inputs: { api_key: 'sk-ant-e2e-test-key' },
    },
  })
  if (createResp.ok()) {
    const cred = (await createResp.json()) as { id: string }
    return { name: credName, id: cred.id }
  }
  throw new Error(`Could not create LLM credential: ${createResp.status()}`)
}

/**
 * Ensure an AAP credential exists via the API.
 * Returns the credential name and id for use in the AAP node form.
 */
export async function ensureAapCredential(page: Page): Promise<{ name: string; id: string }> {
  const targetProjectId = await getBuilderProjectId(page)
  const credName = 'e2e-aap-credential'

  // Check if it already exists under the target project
  const listResp = await apiRequest(page, 'get', `/credentials?name=${encodeURIComponent(credName)}`)
  if (listResp.ok()) {
    const body = (await listResp.json()) as { resources?: Array<{ id: string; name: string; project_id?: string }> }
    const match = body.resources?.find((c) => c.project_id === targetProjectId)
    if (match) return { name: credName, id: match.id }

    if (body.resources?.length) {
      await apiRequest(page, 'delete', `/credentials/${body.resources[0].id}`)
    }
  }

  // Find AAP credential type
  const typesResp = await apiRequest(page, 'get', '/credential_types')
  if (!typesResp.ok()) throw new Error('Could not list credential types')
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  const aapType = types.resources?.find((t) => t.name === 'Ansible Automation Platform')
  if (!aapType) throw new Error('AAP credential type not found')

  const createResp = await apiRequest(page, 'post', '/credentials', {
    data: {
      name: credName,
      credential_type_id: aapType.id,
      project_id: targetProjectId,
      inputs: { oauth_token: 'e2e-test-aap-token' },
    },
  })
  if (createResp.ok()) {
    const cred = (await createResp.json()) as { id: string }
    return { name: credName, id: cred.id }
  }
  throw new Error(`Could not create AAP credential: ${createResp.status()}`)
}

/**
 * Ensure an AAP integration exists, backed by an AAP credential.
 * Returns the integration name for selection in the AAP node form.
 */
export async function ensureAapIntegration(page: Page): Promise<{ name: string; credName: string }> {
  const cred = await ensureAapCredential(page)
  const integrationName = 'e2e-aap-integration'

  // Check if it already exists (mock API uses name[contains] filter)
  const listResp = await apiRequest(
    page,
    'get',
    `/integrations?integration_type=ansible_automation_platform&name%5Bcontains%5D=${encodeURIComponent(integrationName)}`
  )
  if (listResp.ok()) {
    const body = (await listResp.json()) as { resources?: Array<{ id: string; name: string }> }
    const existing = body.resources?.find((i) => i.name === integrationName)
    if (existing) return { name: integrationName, credName: cred.name }
  }

  const createResp = await apiRequest(page, 'post', '/integrations', {
    data: {
      name: integrationName,
      integration_type: 'ansible_automation_platform',
      configuration: {
        integration_type: 'ansible_automation_platform',
        base_url: 'https://example.com',
      },
      management_credential_id: cred.id,
      scope: 'global',
    },
  })
  if (!createResp.ok()) {
    throw new Error(`Could not create AAP integration: ${createResp.status()}`)
  }
  return { name: integrationName, credName: cred.name }
}

export type SeededLlmIntegration = { id: string; name: string }

/**
 * Create an llm_provider integration with a discovered model.
 * The model dropdown in LLMModelSelector requires at least one enabled
 * llm_provider integration with models — without it, all options are disabled.
 *
 * Always creates a new integration (caller provides a unique name).
 * Returns the integration id/name for cleanup in `finally`.
 */
export async function createLlmIntegration(page: Page, name: string): Promise<SeededLlmIntegration> {
  const credential = await ensureLlmCredential(page)
  const createResp = await apiRequest(page, 'post', '/integrations', {
    data: {
      name,
      integration_type: 'llm_provider',
      configuration: {
        integration_type: 'llm_provider',
        provider_hint: 'anthropic',
      },
      management_credential_id: credential.id,
      scope: 'global',
      discovered_models: [
        {
          model_id: 'claude-sonnet-4-20250514',
          name: 'Claude Sonnet 4',
          enabled: true,
        },
      ],
    },
  })
  if (!createResp.ok()) {
    const text = await createResp.text()
    throw new Error(`Could not create LLM integration: ${createResp.status()} ${text}`)
  }
  const integration = (await createResp.json()) as { id: string; name: string }
  return { id: integration.id, name: integration.name }
}

/**
 * Delete an LLM integration by ID. Best-effort — ignores errors.
 */
export async function deleteLlmIntegration(page: Page, integrationId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    await apiRequest(page, 'delete', `/integrations/${integrationId}`)
  } catch {
    // Best-effort cleanup
  }
}

/**
 * Select an LLM model and credential in the Task Agent form.
 *
 * Uses the model picker UX: select model from grouped dropdown,
 * then "Set up connection" to open the credential picker.
 *
 * If no enabled models are available (e.g., in CI environment without LLM integrations),
 * this function will skip the model/credential setup since these tests are focused on
 * v2 schema persistence, not AI agent configuration.
 */
export async function selectLlmCredential(page: Page, credName: string, integrationName?: string) {
  // 1. Open the Model dropdown and check for available models
  const modelToggle = page.getByRole('button', { name: 'Model', exact: true })
  await expect(modelToggle).toBeEnabled({ timeout: 10_000 })
  await modelToggle.click()

  // Pick a model from the correct integration to avoid selecting a model from
  // another parallel worker's integration (which may be deleted during cleanup).
  let modelOption
  if (integrationName) {
    // PF SelectGroup renders as <section><h1>name</h1><ul role="listbox">...</ul></section>.
    // The a11y tree exposes headings + listboxes — not role="group" — so locate
    // the group title text and navigate to its parent <section> for scoped option queries.
    const groupTitle = page.getByText(integrationName, { exact: true })
    await expect(groupTitle).toBeVisible({ timeout: 15_000 })
    const integrationGroup = groupTitle.locator('xpath=..')
    const groupOptions = integrationGroup.locator('[role="option"]:not([aria-disabled="true"])')
    await expect(groupOptions.first()).toBeVisible({ timeout: 5_000 })
    modelOption = groupOptions.first()
  } else {
    // No integration specified — wait for any models and pick the first enabled one
    await page.waitForTimeout(2000)
    const enabledOptions = page.locator('[role="option"]:not([aria-disabled="true"])')
    const enabledCount = await enabledOptions.count()
    if (enabledCount === 0) {
      await page.keyboard.press('Escape')
      return
    }
    modelOption = enabledOptions.first()
  }
  await modelOption.click()

  // 2. Open the credential section via "Set up connection"
  const setupBtn = page.getByRole('button', { name: 'Set up connection' })
  await expect(setupBtn).toBeVisible({ timeout: 5_000 })
  await setupBtn.click()

  // 3. Select the credential from the dropdown.
  // The CredentialSelector fetches with for_action=use, which may take several
  // seconds on resource-constrained backends. Wait for it to be enabled (not
  // just visible) so we don't click while it still shows "Loading credentials...".
  const credDropdown = page.getByRole('button', { name: 'Select a credential' })
  await expect(credDropdown).toBeEnabled({ timeout: 30_000 })
  await credDropdown.click()

  const credOption = page.getByRole('option', { name: credName })
  await expect(credOption).toBeVisible({ timeout: 30_000 })
  await credOption.click()
}
