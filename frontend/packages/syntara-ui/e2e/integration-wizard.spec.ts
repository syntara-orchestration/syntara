import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { createCredentialForIntegrationType, deleteIntegrationViaApi, type SeededCredential } from './seeds/resources'
import { apiRequest, deleteCredentialViaApi, getAuthToken } from './utils/api'

const processEnv: Record<string, string | undefined> = (
  process as unknown as { env: Record<string, string | undefined> }
).env

const isRealBackend = isSkipWebServerForPlaywrightTests()
const openrouterApiKey = processEnv['APP_OPENROUTER_API_KEY']
const openrouterBaseUrl = processEnv['APP_OPENROUTER_BASE_URL'] ?? 'https://openrouter.ai/api/v1'
const mcpServerUrl = processEnv['SYNTARA_E2E_MCP_SERVER_URL']

const WIZARD_URL = '/configuration/integrations/configure'
const INTEGRATIONS_LIST_URL = '/configuration/integrations'

test.describe('Create Integration Wizard', () => {
  test.describe('MCP Server integration', () => {
    test.skip(
      isRealBackend && !mcpServerUrl,
      'SYNTARA_E2E_MCP_SERVER_URL not set; cannot test MCP Server on real backend'
    )

    test('user creates an MCP Server integration through the wizard', async ({ app }) => {
      const integrationName = buildUniqueName('e2e-wizard-mcp')
      const credName = buildUniqueName('e2e-wizard-mcp-cred')
      let credential: SeededCredential | null = null
      let integrationId: string | null = null

      const mcpUrl = isRealBackend ? mcpServerUrl! : 'https://mcp-test.example.com/mcp'

      try {
        credential = await createCredentialForIntegrationType(app, {
          name: credName,
          integrationType: 'mcp_server',
        })
        expect(credential).not.toBeNull()

        await app.goto(toAppUrl(WIZARD_URL))
        await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()
        await expect(app.getByRole('heading', { level: 2, name: 'Integration details' })).toBeVisible()
        await app.getByRole('textbox', { name: 'Server name / ID' }).fill(integrationName)
        await app.getByRole('textbox', { name: 'API URL' }).fill(mcpUrl)

        if (mcpUrl.startsWith('http://')) {
          await app.getByRole('button', { name: 'Security' }).click()
          await app.getByRole('checkbox', { name: 'Allow HTTP connections' }).check()
        }

        await app.getByRole('button', { name: 'Next' }).click()
        await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()

        await app.getByRole('button', { name: 'Health check credential', exact: true }).click()
        await app.getByRole('option', { name: credName }).click()

        await app.getByRole('button', { name: 'Test connection' }).click()
        await expect(app.getByRole('button', { name: 'Next' })).toBeEnabled({ timeout: 30_000 })
        await app.getByRole('button', { name: 'Next' }).click()

        await expect(app.getByRole('button', { name: 'Save' })).toBeVisible()
        const responsePromise = app.waitForResponse('**/api/v1/integrations')
        await app.getByRole('button', { name: 'Save' }).click()
        const response = await responsePromise
        integrationId = ((await response.json()) as { id?: string }).id ?? null

        await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))
        await app.getByPlaceholder('Filter by name').fill(integrationName)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(integrationName) })).toBeVisible()
      } finally {
        if (integrationId) await deleteIntegrationViaApi(app, integrationId)
        if (credential) await deleteCredentialViaApi(app, credential.id)
      }
    })
  })

  test.describe('LLM Provider integration', () => {
    test.skip(
      isRealBackend && !openrouterApiKey,
      'APP_OPENROUTER_API_KEY not set; cannot test LLM Provider on real backend'
    )

    test('user creates an LLM Provider integration through the wizard', async ({ app }) => {
      const integrationName = buildUniqueName('e2e-wizard-llm')
      const credName = buildUniqueName('e2e-wizard-llm-cred')
      let credential: SeededCredential | null = null
      let integrationId: string | null = null

      const apiUrl = isRealBackend ? openrouterBaseUrl : 'https://llm-test.example.com/v1'

      try {
        credential = await createCredentialForIntegrationType(app, {
          name: credName,
          integrationType: 'llm_provider',
          apiKey: isRealBackend ? openrouterApiKey : undefined,
        })
        expect(credential).not.toBeNull()

        await app.goto(toAppUrl(WIZARD_URL))
        await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

        await app.getByRole('button', { name: 'MCP Server' }).click()
        await app.getByRole('option', { name: 'LLM Provider' }).click()

        await app.getByRole('button', { name: 'Red Hat AI' }).click()
        await app.getByRole('option', { name: 'Custom' }).click()

        await app.getByRole('textbox', { name: 'Name' }).fill(integrationName)
        await app.getByRole('textbox', { name: 'API URL' }).fill(apiUrl)
        await app.getByRole('button', { name: 'Next' }).click()

        await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()
        await app.getByRole('button', { name: 'Health check credential', exact: true }).click()
        await app.getByRole('option', { name: credName }).click()

        await app.getByRole('button', { name: 'Test connection' }).click()
        await expect(app.getByRole('button', { name: 'Next' })).toBeEnabled({ timeout: 30_000 })
        await app.getByRole('button', { name: 'Next' }).click()

        await expect(app.getByRole('button', { name: 'Save' })).toBeVisible()
        const responsePromise = app.waitForResponse('**/api/v1/integrations')
        await app.getByRole('button', { name: 'Save' }).click()
        const response = await responsePromise
        integrationId = ((await response.json()) as { id?: string }).id ?? null

        await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))
        await app.getByPlaceholder('Filter by name').fill(integrationName)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(integrationName) })).toBeVisible()
      } finally {
        if (integrationId) await deleteIntegrationViaApi(app, integrationId)
        if (credential) await deleteCredentialViaApi(app, credential.id)
      }
    })
  })

  test.describe('AAP Gateway integration', () => {
    test.skip(isRealBackend, 'AAP Gateway not available in upstream test environment')

    test('user creates an AAP Gateway integration through the wizard', async ({ app }) => {
      const integrationName = buildUniqueName('e2e-wizard-aap')
      const credName = buildUniqueName('e2e-wizard-aap-cred')
      let credential: SeededCredential | null = null
      let integrationId: string | null = null

      try {
        credential = await createCredentialForIntegrationType(app, {
          name: credName,
          integrationType: 'aap_gateway',
        })
        expect(credential).not.toBeNull()

        await app.goto(toAppUrl(WIZARD_URL))
        await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

        await app.getByRole('button', { name: 'MCP Server' }).click()
        await app.getByRole('option', { name: 'Ansible Automation Platform' }).click()

        await app.getByRole('textbox', { name: 'Server name / ID' }).fill(integrationName)
        await app.getByRole('textbox', { name: 'API URL' }).fill('https://aap.example.com')
        await app.getByRole('button', { name: 'Next' }).click()

        await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()
        await app.getByRole('button', { name: 'Health check credential', exact: true }).click()
        await app.getByRole('option', { name: credName }).click()

        await app.getByRole('button', { name: 'Test connection' }).click()

        const saveButton = app.getByRole('button', { name: 'Save' })
        await expect(saveButton).toBeEnabled({ timeout: 30_000 })
        const responsePromise = app.waitForResponse('**/api/v1/integrations')
        await saveButton.click()
        const response = await responsePromise
        integrationId = ((await response.json()) as { id?: string }).id ?? null

        await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))
        await app.getByPlaceholder('Filter by name').fill(integrationName)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(integrationName) })).toBeVisible()
      } finally {
        if (integrationId) await deleteIntegrationViaApi(app, integrationId)
        if (credential) await deleteCredentialViaApi(app, credential.id)
      }
    })
  })
})

test('credential created inline during wizard persists after wizard abandonment', async ({ app }) => {
  const credName = buildUniqueName('e2e-wizard-orphan-cred')
  let orphanedCredentialId: string | null = null

  try {
    await app.goto(toAppUrl(WIZARD_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

    await app.getByRole('button', { name: 'MCP Server' }).click()
    await app.getByRole('option', { name: 'LLM Provider' }).click()
    await app.getByRole('button', { name: 'Red Hat AI' }).click()
    await app.getByRole('option', { name: 'Custom' }).click()
    await app.getByRole('textbox', { name: 'Name' }).fill(buildUniqueName('e2e-wizard-abandon'))
    await app.getByRole('textbox', { name: 'API URL' }).fill('https://llm-test.example.com/v1')
    await app.getByRole('button', { name: 'Next' }).click()

    await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()
    await app.getByRole('button', { name: 'Health check credential', exact: true }).click()

    const createOption = app.getByRole('option', { name: /create/i })
    await expect(createOption).toBeVisible()
    await createOption.click()

    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('textbox', { name: /name/i }).fill(credName)

    const projectDropdown = dialog.getByRole('button', { name: 'Credential project' })
    await projectDropdown.click()
    const projectOption = app.getByRole('option', { name: 'default' })
    await expect(projectOption).toBeVisible()
    await projectOption.click()

    await dialog.getByPlaceholder('Enter API key').fill('sk-orphan-test-key')

    const createButton = dialog.getByRole('button', { name: /create credential/i })
    await expect(createButton).toBeEnabled()
    await createButton.click()

    await expect(dialog).not.toBeVisible()

    // Abandon the wizard
    await app.goto(toAppUrl(INTEGRATIONS_LIST_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    const token = await getAuthToken(app)
    expect(token).toBeTruthy()

    const resp = await apiRequest(app, 'get', `/credentials?name[contains]=${encodeURIComponent(credName)}`, {
      token: token!,
    })
    expect(resp.ok()).toBe(true)
    const body = (await resp.json()) as { resources?: Array<{ id: string; name: string }> }
    const found = body.resources?.find((c) => c.name === credName)
    expect(found).toBeTruthy()
    orphanedCredentialId = found?.id ?? null
  } finally {
    if (orphanedCredentialId) await deleteCredentialViaApi(app, orphanedCredentialId)
  }
})

test.describe('HTTP URL Rejection and Allow HTTP Override', () => {
  const integrationTypes = [
    { type: 'MCP Server', nameLabel: 'Server name / ID' },
    { type: 'LLM Provider', nameLabel: 'Name' },
    { type: 'Ansible Automation Platform', nameLabel: 'Server name / ID' },
  ] as const

  for (const { type, nameLabel } of integrationTypes) {
    test(`${type}: HTTP URL is rejected by default, Allow HTTP overrides`, async ({ app }) => {
      await app.goto(toAppUrl(WIZARD_URL))
      await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

      if (type !== 'MCP Server') {
        await app.getByRole('button', { name: 'MCP Server' }).click()
        await app.getByRole('option', { name: type }).click()
      }

      if (type === 'LLM Provider') {
        await app.getByRole('button', { name: 'Red Hat AI' }).click()
        await app.getByRole('option', { name: 'Custom' }).click()
      }

      await app.getByRole('textbox', { name: nameLabel }).fill(buildUniqueName('e2e-http-test'))
      await app.getByRole('textbox', { name: 'API URL' }).fill('http://insecure.example.com/api')

      await app.getByRole('button', { name: 'Next' }).click()
      await expect(app.getByText('Must be an HTTPS URL')).toBeVisible()
      await expect(app.getByRole('heading', { level: 2, name: 'Integration details' })).toBeVisible()

      await app.getByRole('button', { name: 'Security' }).click()
      await app.getByRole('checkbox', { name: 'Allow HTTP connections' }).check()

      await app.getByRole('button', { name: 'Next' }).click()
      await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()
    })
  }
})

test('discovery failure shows error state, retry after correction succeeds', async ({ app }) => {
  // Mock-only: after the injected discover failure is cleared, the "retry" step expects a real
  // discover to succeed, which requires a reachable, live LLM endpoint. The real-backend E2E
  // environment has none (and an unresolvable placeholder host is rejected by SSRF validation),
  // so this UX flow cannot be exercised there.
  test.skip(isRealBackend, 'Retry requires a live LLM endpoint not available on the real backend')

  const integrationName = buildUniqueName('e2e-wizard-retry')
  const credName = buildUniqueName('e2e-wizard-retry-cred')
  let credential: SeededCredential | null = null
  let integrationId: string | null = null

  try {
    credential = await createCredentialForIntegrationType(app, {
      name: credName,
      integrationType: 'llm_provider',
    })
    expect(credential).not.toBeNull()

    await app.goto(toAppUrl(WIZARD_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Configure integration' })).toBeVisible()

    await app.getByRole('button', { name: 'MCP Server' }).click()
    await app.getByRole('option', { name: 'LLM Provider' }).click()
    await app.getByRole('button', { name: 'Red Hat AI' }).click()
    await app.getByRole('option', { name: 'Custom' }).click()
    await app.getByRole('textbox', { name: 'Name' }).fill(integrationName)
    await app.getByRole('textbox', { name: 'API URL' }).fill('https://llm-test.example.com/v1')
    await app.getByRole('button', { name: 'Next' }).click()

    await expect(app.getByRole('heading', { level: 2, name: 'Connection credential' })).toBeVisible()
    await app.getByRole('button', { name: 'Health check credential', exact: true }).click()
    await app.getByRole('option', { name: credName }).click()

    await app.route('**/api/v1/integrations/discover', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          checked_at: new Date().toISOString(),
          error: 'Connection refused',
        }),
      })
    )

    await app.getByRole('button', { name: 'Test connection' }).click()
    await expect(app.getByRole('heading', { name: /connection failed/i })).toBeVisible()

    await app.getByRole('button', { name: 'Next' }).click()
    await expect(app.getByRole('heading', { name: /connection test failed/i })).toBeVisible()

    await app.unroute('**/api/v1/integrations/discover')

    await app.getByRole('button', { name: 'Retry connection' }).click()
    await expect(app.getByRole('button', { name: 'Save' })).toBeEnabled({ timeout: 30_000 })
    const responsePromise = app.waitForResponse('**/api/v1/integrations')
    await app.getByRole('button', { name: 'Save' }).click()
    const response = await responsePromise
    integrationId = ((await response.json()) as { id?: string }).id ?? null

    await expect(app).toHaveURL(new RegExp(INTEGRATIONS_LIST_URL))
    await app.getByPlaceholder('Filter by name').fill(integrationName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(app.getByRole('row', { name: new RegExp(integrationName) })).toBeVisible()
  } finally {
    if (integrationId) await deleteIntegrationViaApi(app, integrationId)
    if (credential) await deleteCredentialViaApi(app, credential.id)
  }
})
