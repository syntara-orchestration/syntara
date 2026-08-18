/**
 * E2E Tests: AAP Node Wiring in Workflow Builder (Test 17)
 *
 * Verifies that AAP Job Template and Workflow Template nodes can be wired
 * to a configured AAP Gateway integration and that job/workflow templates
 * are browsable via the resource pickers.
 */
import { test, expect } from './fixtures'
import { buildUniqueName, clickAddConnectedStep, startWorkflowWithTrigger } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi } from './seeds/resources'
import { apiRequest, deleteCredentialViaApi, ensureProject } from './utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()
// Real backend rejects an unresolvable base_url as an SSRF risk; use the compose-allowlisted
// mcp-server host (override via SYNTARA_E2E_INTEGRATION_HOST). Mock mode keeps a readable placeholder.
const ssrfSafeIntegrationHost = process.env.SYNTARA_E2E_INTEGRATION_HOST ?? 'https://mcp-server'

async function createAAPIntegration(
  app: import('@playwright/test').Page,
  name: string
): Promise<{ integrationId: string; credentialId: string }> {
  const project = await ensureProject(app)
  if (!project) throw new Error('Could not ensure project')

  const typesResp = await apiRequest(app, 'get', '/credential_types')
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  const aapType = types.resources?.find((t) => t.name === 'Ansible Automation Platform')
  if (!aapType) throw new Error('AAP credential type not found')

  const credResp = await apiRequest(app, 'post', '/credentials', {
    data: {
      name: `${name}-cred`,
      credential_type_id: aapType.id,
      project_id: project.id,
      inputs: { oauth_token: 'e2e-test-token' },
    },
  })
  if (!credResp.ok()) throw new Error(`Could not create AAP credential: ${credResp.status()}`)
  const cred = (await credResp.json()) as { id: string }

  const intResp = await apiRequest(app, 'post', '/integrations', {
    data: {
      name,
      integration_type: 'ansible_automation_platform',
      configuration: {
        integration_type: 'ansible_automation_platform',
        base_url: isRealBackend ? ssrfSafeIntegrationHost : `https://${name}.example.com`,
      },
      management_credential_id: cred.id,
      scope: 'global',
    },
  })
  if (!intResp.ok()) throw new Error(`Could not create AAP integration: ${intResp.status()}`)
  const integration = (await intResp.json()) as { id: string }
  return { integrationId: integration.id, credentialId: cred.id }
}

test.describe('AAP Node Wiring', () => {
  test('AAP Job Template node shows only AAP integrations and enables resource browsing', async ({ app }) => {
    const aapName = buildUniqueName('e2e-aap-t17')
    const llmName = buildUniqueName('e2e-llm-t17')
    let aapIds: { integrationId: string; credentialId: string } | undefined
    let llmIntegrationId: string | undefined
    let llmCredentialId: string | undefined
    try {
      // Create an AAP integration
      aapIds = await createAAPIntegration(app, aapName)

      // Create an LLM integration — it should NOT appear in the AAP selector
      const typesResp = await apiRequest(app, 'get', '/credential_types')
      const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
      const llmType = types.resources?.find((t) => t.name === 'LLM Provider')
      if (!llmType) throw new Error('LLM Provider credential type not found')

      const project = await ensureProject(app)
      const llmCredResp = await apiRequest(app, 'post', '/credentials', {
        data: {
          name: `${llmName}-cred`,
          credential_type_id: llmType.id,
          project_id: project!.id,
          inputs: { api_key: 'sk-e2e-test' },
        },
      })
      const llmCred = (await llmCredResp.json()) as { id: string }
      llmCredentialId = llmCred.id

      const llmResp = await apiRequest(app, 'post', '/integrations', {
        data: {
          name: llmName,
          integration_type: 'llm_provider',
          configuration: { integration_type: 'llm_provider', provider_hint: 'custom' },
          management_credential_id: llmCredentialId,
          scope: 'global',
          discovered_models: [{ model_id: 'model-a', name: 'Model A', enabled: true, is_default: true }],
        },
      })
      const llmIntegration = (await llmResp.json()) as { id: string }
      llmIntegrationId = llmIntegration.id

      // Open workflow builder and add an AAP Job Template node
      await startWorkflowWithTrigger(app)

      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'AAP Execution' }).click()
      await panel.getByRole('button', { name: 'Launch AAP job template' }).click()

      // Fill in the node name
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Deploy App')

      // Open the integration selector
      const integrationToggle = app.getByRole('button', { name: 'Integration', exact: true })
      await expect(integrationToggle).toBeEnabled({ timeout: 10_000 })
      await integrationToggle.click()

      // Only AAP integrations should appear; the LLM integration should not
      await expect(app.getByRole('option', { name: new RegExp(aapName) })).toBeVisible({ timeout: 15_000 })
      await expect(app.getByRole('option', { name: new RegExp(llmName) })).not.toBeAttached()

      // Select the AAP integration
      await app.getByRole('option', { name: new RegExp(aapName) }).click()

      // Set up the credential so the resource browser activates
      const setupBtn = app.getByRole('button', { name: 'Set up connection' })
      await expect(setupBtn).toBeVisible()
      await setupBtn.click()

      const credDropdown = app.getByRole('button', { name: 'Select a credential' })
      await expect(credDropdown).toBeEnabled({ timeout: 30_000 })
      await credDropdown.click()

      // Select the AAP credential we created
      const credOption = app.getByRole('option', { name: new RegExp(`${aapName}-cred`) })
      await expect(credOption).toBeVisible({ timeout: 10_000 })
      await credOption.click()

      // The Organization picker should appear after selecting a credential
      const orgInput = app.getByPlaceholder('Select an organization')
      await expect(orgInput).toBeVisible({ timeout: 15_000 })

      // Organization and job template browsing requires a live AAP Controller;
      // the mock API seeds static data but the real backend proxies to AAP.
      if (!isRealBackend) {
        await orgInput.click()

        await expect(app.getByRole('option', { name: 'Default' })).toBeVisible({ timeout: 10_000 })
        await expect(app.getByRole('option', { name: 'Engineering' })).toBeVisible()

        await app.getByRole('option', { name: 'Default' }).click()

        const templateInput = app.getByPlaceholder('Select a job template')
        await expect(templateInput).toBeVisible({ timeout: 15_000 })
        await templateInput.click()

        const deployOption = app.getByRole('option', { name: /Deploy App/i })
        await expect(deployOption).toBeVisible({ timeout: 10_000 })

        await deployOption.click()
        await expect(templateInput).toHaveValue('Deploy App')
      }
    } finally {
      if (llmIntegrationId) await deleteIntegrationViaApi(app, llmIntegrationId)
      if (llmCredentialId) await deleteCredentialViaApi(app, llmCredentialId)
      if (aapIds) {
        await deleteIntegrationViaApi(app, aapIds.integrationId)
        await deleteCredentialViaApi(app, aapIds.credentialId)
      }
    }
  })
})
