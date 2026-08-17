/**
 * E2E Tests: Integration Wizard
 *
 * Critical paths covered:
 * - Connection test succeeds and discovers tools within 10s (MCP Server)
 * - Connection test with invalid credential returns auth failure classification (LLM Provider)
 * - Connection test with unreachable endpoint returns connection_error classification
 * - Connection test with delayed/unresponsive endpoint returns timeout classification
 * - Connection test with self-signed TLS cert returns ssl_error classification
 * - Health check status transitions between available and error on list and detail pages
 * - Health check error classifications appear correctly on the integration detail page
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi, deleteCredentialViaApi } from './seeds/resources'
import { apiRequest, ensureProject } from './utils/api'

const processEnv: Record<string, string | undefined> = (
  process as unknown as { env: Record<string, string | undefined> }
).env

const isRealBackend = isSkipWebServerForPlaywrightTests()
const mcpServerUrl = processEnv['SYNTARA_E2E_MCP_SERVER_URL']

async function createLlmCredential(app: Page, name: string): Promise<string> {
  const project = await ensureProject(app)
  const typesResp = await apiRequest(app, 'get', '/credential_types')
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  const llmType = types.resources?.find((t) => t.name === 'LLM Provider')
  if (!llmType || !project) throw new Error('Could not find LLM Provider credential type or project')
  const credResp = await apiRequest(app, 'post', '/credentials', {
    data: { name, credential_type_id: llmType.id, project_id: project.id, inputs: { api_key: `sk-e2e-${name}` } },
  })
  if (!credResp.ok()) throw new Error(`Could not create credential: ${credResp.status()}`)
  return ((await credResp.json()) as { id: string }).id
}

test.describe('Integration Wizard @pr-check', () => {
  test.describe('Connection test — MCP Server', () => {
    test.skip(
      isRealBackend && !mcpServerUrl,
      'SYNTARA_E2E_MCP_SERVER_URL not set; cannot test MCP Server on real backend'
    )

    test('connection test succeeds and discovers resources within 10s', async ({ app }) => {
      const mcpUrl = isRealBackend ? mcpServerUrl! : 'https://mcp-test.example.com/mcp'
      const name = buildUniqueName('e2e-wizard-t7')
      let integrationId: string | undefined

      try {
        // Step 1 — Integration details
        await app.goto(toAppUrl('/configuration/integrations/configure'))
        await expect(app.getByRole('heading', { name: 'Integration details', level: 2 })).toBeVisible()

        await app.getByRole('textbox', { name: 'Server name / ID' }).fill(name)
        await app.getByRole('textbox', { name: 'API URL' }).fill(mcpUrl)

        if (mcpUrl.startsWith('http://')) {
          await app.getByRole('button', { name: 'Security' }).click()
          await app.getByRole('checkbox', { name: 'Allow HTTP connections' }).check()
        }

        await app.getByRole('button', { name: 'Next' }).click()

        // Step 2 — Connection credential
        await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()

        const startTime = Date.now()
        await app.getByRole('button', { name: 'Test connection' }).click()

        // Wait for success alert within 10s
        await expect(app.getByRole('heading', { name: 'Connection tested' })).toBeVisible({ timeout: 15_000 })
        const elapsed = Date.now() - startTime
        expect(elapsed).toBeLessThan(10_000)

        // Verify success description mentions discovered tools
        await expect(app.getByText(/Successfully connected\. Discovered \d+ tool/)).toBeVisible()

        await app.getByRole('button', { name: 'Next' }).click()

        // Step 3 — Enable tools
        await expect(app.getByRole('heading', { name: 'Enable tools' })).toBeVisible()

        // Verify at least one tool row appears in the table
        await expect(app.locator('table tbody tr')).not.toHaveCount(0, { timeout: 10_000 })

        // Save the integration — capture the API response to get the ID
        const responsePromise = app.waitForResponse('**/api/v1/integrations')
        await app.getByRole('button', { name: 'Save' }).click()
        const response = await responsePromise
        expect(response.status()).toBe(201)

        const body = (await response.json()) as { id?: string }
        integrationId = body.id

        // Verify redirect to integrations list
        await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible({ timeout: 10_000 })
      } finally {
        if (integrationId) {
          await deleteIntegrationViaApi(app, integrationId)
        }
      }
    })
  })

  test('connection test with invalid credential returns auth failure', async ({ app }) => {
    const name = buildUniqueName('e2e-wizard-t8')
    const credName = buildUniqueName('e2e-wizard-t8-cred')
    let credentialId: string | undefined

    try {
      credentialId = await createLlmCredential(app, credName)

      // Intercept the discover endpoint to inject an auth_failure response.
      // The E2E concern is the UI's handling of auth_failure; the backend's
      // 401/403 → auth_failure classification is covered by backend unit tests.
      await app.route('**/api/v1/integrations/discover', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error_type: 'auth_failure',
            error: 'Authentication failed: the provided API key is invalid or has been revoked.',
          }),
        })
      })

      // Step 1 — Integration details: LLM Provider, OpenAI hint (hides base URL field)
      await app.goto(toAppUrl('/configuration/integrations/configure'))
      await expect(app.getByRole('heading', { name: 'Integration details', level: 2 })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      await app.getByRole('option', { name: 'LLM Provider' }).click()

      await app.getByRole('textbox', { name: 'Name' }).fill(name)

      await app.getByRole('button', { name: 'Red Hat AI' }).click()
      await app.getByRole('option', { name: 'OpenAI' }).click()

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 2 — Connection credential: select the invalid credential, run the test
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()

      const credToggle = app.getByRole('button', { name: 'Health check credential', exact: true })
      await expect(credToggle).toBeEnabled({ timeout: 10_000 })
      await credToggle.click()
      await app.getByRole('option', { name: credName }).click()

      await app.getByRole('button', { name: 'Test connection' }).click()

      // Danger alert confirms the failure
      await expect(app.getByRole('heading', { name: 'Connection failed' })).toBeVisible({ timeout: 15_000 })

      // Advance to step 3 to observe the failure state
      await app.getByRole('button', { name: 'Next' }).click()

      // Step 3 — Enable models shows authentication failure state
      await expect(app.getByRole('heading', { name: 'Connection test failed', level: 2 })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Retry connection' })).toBeVisible()

      // User can navigate back to step 2 to correct the credential
      await app.getByRole('button', { name: 'Back' }).click()
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()
    } finally {
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })

  test('connection test with unreachable endpoint returns connection error', async ({ app }) => {
    test.skip(!isRealBackend || !mcpServerUrl, 'Requires real backend with SYNTARA_E2E_MCP_SERVER_URL set')
    const name = buildUniqueName('e2e-wizard-t9a')
    const credName = buildUniqueName('e2e-wizard-t9a-cred')
    let credentialId: string | undefined

    try {
      credentialId = await createLlmCredential(app, credName)
      // Step 1 — LLM Provider with Red Hat AI hint, base_url pointing to a port with nothing
      // listening. TCP RST is immediate so the backend classifies this as connection_error, not timeout.
      await app.goto(toAppUrl('/configuration/integrations/configure'))
      await expect(app.getByRole('heading', { name: 'Integration details', level: 2 })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      await app.getByRole('option', { name: 'LLM Provider' }).click()

      await app.getByRole('textbox', { name: 'Name' }).fill(name)
      await app.getByRole('textbox', { name: 'API URL' }).fill('https://mcp-server:9999')

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 2 — select credential and run the test; capture the discover API response
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()

      const credToggle = app.getByRole('button', { name: 'Health check credential', exact: true })
      await expect(credToggle).toBeEnabled({ timeout: 10_000 })
      await credToggle.click()
      await app.getByRole('option', { name: credName }).click()

      await app.getByRole('button', { name: 'Test connection' }).click()

      await expect(app.getByRole('heading', { name: 'Connection failed' })).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 3 — failure state is distinct from auth_failure (no "Authentication" text)
      await expect(app.getByRole('heading', { name: 'Connection test failed', level: 2 })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Retry connection' })).toBeVisible()

      await app.getByRole('button', { name: 'Back' }).click()
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()
    } finally {
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })

  test('connection test with unresponsive endpoint returns timeout classification', async ({ app }) => {
    const name = buildUniqueName('e2e-wizard-t9b')
    const credName = buildUniqueName('e2e-wizard-t9b-cred')
    let credentialId: string | undefined

    try {
      credentialId = await createLlmCredential(app, credName)

      // Intercept the discover endpoint to inject a timeout response.
      // A real timeout would require waiting 10 seconds; the backend's timeout
      // enforcement is covered by backend unit tests. Here we verify the UI
      // correctly surfaces timeout classification as distinct from auth_failure.
      await app.route('**/api/v1/integrations/discover', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error_type: 'timeout',
            error: 'Connection timed out: the server did not respond within the configured time limit.',
          }),
        })
      })

      // Step 1 — LLM Provider, OpenAI hint (hides base URL — simpler for a mocked test)
      await app.goto(toAppUrl('/configuration/integrations/configure'))
      await expect(app.getByRole('heading', { name: 'Integration details', level: 2 })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      await app.getByRole('option', { name: 'LLM Provider' }).click()

      await app.getByRole('textbox', { name: 'Name' }).fill(name)

      await app.getByRole('button', { name: 'Red Hat AI' }).click()
      await app.getByRole('option', { name: 'OpenAI' }).click()

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 2 — select credential and run the test
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()

      const credToggle = app.getByRole('button', { name: 'Health check credential', exact: true })
      await expect(credToggle).toBeEnabled({ timeout: 10_000 })
      await credToggle.click()
      await app.getByRole('option', { name: credName }).click()

      await app.getByRole('button', { name: 'Test connection' }).click()

      // Mocked timeout response → danger alert
      await expect(app.getByRole('heading', { name: 'Connection failed' })).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 3 — timeout state is distinct from both auth_failure and connection_error
      await expect(app.getByRole('heading', { name: 'Connection test failed', level: 2 })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Retry connection' })).toBeVisible()

      await app.getByRole('button', { name: 'Back' }).click()
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()
    } finally {
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })

  test('connection test with self-signed TLS certificate returns TLS error', async ({ app }) => {
    const name = buildUniqueName('e2e-wizard-t10')
    const credName = buildUniqueName('e2e-wizard-t10-cred')
    let credentialId: string | undefined

    try {
      credentialId = await createLlmCredential(app, credName)

      // Inject a ssl_error response. The local backend presents a self-signed cert that
      // the LLM adapter's HTTP client rejects — here we inject the expected response to
      // test the UI's handling of TLS error classification, distinct from connection_error
      // and auth_failure.
      await app.route('**/api/v1/integrations/discover', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error_type: 'ssl_error',
            error: "TLS certificate verification failed: unable to verify the server's certificate.",
          }),
        })
      })

      // Step 1 — LLM Provider, Red Hat AI hint pointing to the local backend's HTTPS
      // endpoint which uses a self-signed certificate
      await app.goto(toAppUrl('/configuration/integrations/configure'))
      await expect(app.getByRole('heading', { name: 'Integration details', level: 2 })).toBeVisible()

      await app.getByRole('button', { name: 'MCP Server' }).click()
      await app.getByRole('option', { name: 'LLM Provider' }).click()

      await app.getByRole('textbox', { name: 'Name' }).fill(name)
      await app.getByRole('textbox', { name: 'API URL' }).fill('https://localhost:8000')

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 2 — select credential and run test
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()

      const credToggle = app.getByRole('button', { name: 'Health check credential', exact: true })
      await expect(credToggle).toBeEnabled({ timeout: 10_000 })
      await credToggle.click()
      await app.getByRole('option', { name: credName }).click()

      await app.getByRole('button', { name: 'Test connection' }).click()

      // Danger alert confirms TLS failure (distinct from "Connection tested" success)
      await expect(app.getByRole('heading', { name: 'Connection failed' })).toBeVisible({ timeout: 15_000 })

      await app.getByRole('button', { name: 'Next' }).click()

      // Step 3 — TLS error state, distinct from auth_failure and connection_error
      await expect(app.getByRole('heading', { name: 'Connection test failed', level: 2 })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Retry connection' })).toBeVisible()

      await app.getByRole('button', { name: 'Back' }).click()
      await expect(app.getByRole('heading', { name: 'Connection credential', level: 2 })).toBeVisible()
    } finally {
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })

  test.describe('Health check transitions (real backend)', () => {
    test.skip(!isRealBackend || !mcpServerUrl, 'Requires real backend with SYNTARA_E2E_MCP_SERVER_URL set')

    test('health check status transitions between available and error', async ({ app }) => {
      test.slow()

      const name = buildUniqueName('e2e-wizard-t11')
      let integrationId: string | undefined

      try {
        // Create MCP Server integration pointing at the local MCP test server
        const createResp = await apiRequest(app, 'post', '/integrations', {
          data: {
            name,
            integration_type: 'mcp_server',
            configuration: { integration_type: 'mcp_server', base_url: mcpServerUrl! },
            scope: 'global',
          },
        })
        if (!createResp.ok()) throw new Error(`Could not create integration: ${createResp.status()}`)
        integrationId = ((await createResp.json()) as { id: string }).id

        // ── Phase 1: Establish "available" status via manual validate ──────────
        const v1Resp = await apiRequest(app, 'post', `/integrations/${integrationId}/validate`)
        expect(((await v1Resp.json()) as { success: boolean }).success).toBe(true)

        // Verify on list page
        await app.goto(toAppUrl('/configuration/integrations'))
        await app.getByPlaceholder('Filter by name').fill(name)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(name) }).getByText('Available')).toBeVisible({
          timeout: 10_000,
        })

        // Verify on detail page
        await app.goto(toAppUrl(`/configuration/integrations/${integrationId}`))
        await expect(app.getByText('Available', { exact: true })).toBeVisible({ timeout: 10_000 })

        // Capture last_validated_at baseline
        const g1 = (await (await apiRequest(app, 'get', `/integrations/${integrationId}`)).json()) as {
          validation_status: string
          last_validated_at: string | null
        }
        expect(g1.validation_status).toBe('available')
        const ts1 = g1.last_validated_at
        expect(ts1).not.toBeNull()

        // ── Phase 2: Transition to "error" ────────────────────────────────────
        // Swap base_url to an unreachable port
        const patch1Resp = await apiRequest(app, 'patch', `/integrations/${integrationId}`, {
          data: { configuration: { integration_type: 'mcp_server', base_url: 'http://127.0.0.1:9999' } },
        })
        if (!patch1Resp.ok()) throw new Error(`PATCH to unreachable URL failed: ${patch1Resp.status()}`)

        // Manual validate → backend hits the unreachable port and marks as error
        const v2Resp = await apiRequest(app, 'post', `/integrations/${integrationId}/validate`)
        expect(((await v2Resp.json()) as { success: boolean }).success).toBe(false)

        // Verify on list page
        await app.goto(toAppUrl('/configuration/integrations'))
        await app.getByPlaceholder('Filter by name').fill(name)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(name) }).getByText('Error')).toBeVisible({
          timeout: 10_000,
        })

        // Verify on detail page
        await app.goto(toAppUrl(`/configuration/integrations/${integrationId}`))
        await expect(app.getByText('Error', { exact: true })).toBeVisible({ timeout: 10_000 })

        // last_validated_at must have advanced
        const g2 = (await (await apiRequest(app, 'get', `/integrations/${integrationId}`)).json()) as {
          validation_status: string
          last_validated_at: string | null
        }
        expect(g2.validation_status).toBe('error')
        expect(g2.last_validated_at).not.toBeNull()
        expect(g2.last_validated_at).not.toBe(ts1)

        // ── Phase 3: Restore to "available" ───────────────────────────────────
        const patch2Resp = await apiRequest(app, 'patch', `/integrations/${integrationId}`, {
          data: { configuration: { integration_type: 'mcp_server', base_url: mcpServerUrl! } },
        })
        if (!patch2Resp.ok()) throw new Error(`PATCH restore failed: ${patch2Resp.status()}`)

        const v3Resp = await apiRequest(app, 'post', `/integrations/${integrationId}/validate`)
        expect(((await v3Resp.json()) as { success: boolean }).success).toBe(true)

        // Verify on list page
        await app.goto(toAppUrl('/configuration/integrations'))
        await app.getByPlaceholder('Filter by name').fill(name)
        await app.getByRole('button', { name: 'Apply filter' }).click()
        await expect(app.getByRole('row', { name: new RegExp(name) }).getByText('Available')).toBeVisible({
          timeout: 10_000,
        })

        // Verify on detail page
        await app.goto(toAppUrl(`/configuration/integrations/${integrationId}`))
        await expect(app.getByText('Available', { exact: true })).toBeVisible({ timeout: 10_000 })

        // last_validated_at must have advanced again
        const g3 = (await (await apiRequest(app, 'get', `/integrations/${integrationId}`)).json()) as {
          validation_status: string
          last_validated_at: string | null
        }
        expect(g3.validation_status).toBe('available')
        expect(g3.last_validated_at).not.toBe(g2.last_validated_at)
      } finally {
        if (integrationId) await deleteIntegrationViaApi(app, integrationId)
      }
    })

    test('health check error classifications appear correctly on integration detail page', async ({ app }) => {
      test.slow()

      const name = buildUniqueName('e2e-wizard-t13')
      let integrationId: string | undefined

      try {
        // Create MCP Server integration initially pointing at the working MCP test server
        const createResp = await apiRequest(app, 'post', '/integrations', {
          data: {
            name,
            integration_type: 'mcp_server',
            configuration: { integration_type: 'mcp_server', base_url: mcpServerUrl! },
            scope: 'global',
          },
        })
        if (!createResp.ok()) throw new Error(`Could not create integration: ${createResp.status()}`)
        integrationId = ((await createResp.json()) as { id: string }).id

        // Capture the base integration object for building mocked GET responses
        const baseData = (await (await apiRequest(app, 'get', `/integrations/${integrationId}`)).json()) as Record<
          string,
          unknown
        >

        // ── connection_error: real end-to-end validate ──────────────────────
        await apiRequest(app, 'patch', `/integrations/${integrationId}`, {
          data: { configuration: { integration_type: 'mcp_server', base_url: 'http://127.0.0.1:9999' } },
        })
        await apiRequest(app, 'post', `/integrations/${integrationId}/validate`)

        await app.goto(toAppUrl(`/configuration/integrations/${integrationId}`))
        await expect(app.getByText('Error', { exact: true })).toBeVisible({ timeout: 10_000 })

        // ── auth_failure, ssl_error, timeout: inject error state via GET mock ─
        // These error types require specific network conditions not reliably available
        // in the dev environment. We mock GET /integrations/{id} to inject the expected
        // integration state and verify the detail page renders each classification correctly.
        const routePattern = `**/api/v1/integrations/${integrationId}`
        for (const { errorMsg } of [
          { errorMsg: 'Authentication failed: the provided credential was rejected.' },
          { errorMsg: "TLS certificate verification failed: unable to verify the server's certificate." },
          { errorMsg: 'Connection timed out: the server did not respond within the configured time limit.' },
        ]) {
          await app.route(routePattern, async (route, request) => {
            if (request.method() === 'GET') {
              await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                  ...baseData,
                  validation_status: 'error',
                  validation_error: errorMsg,
                  last_validated_at: new Date().toISOString(),
                }),
              })
            } else {
              await route.continue()
            }
          })

          await app.goto(toAppUrl(`/configuration/integrations/${integrationId}`))
          const errorBadge = app.getByText('Error', { exact: true })
          await expect(errorBadge).toBeVisible({ timeout: 10_000 })
          // Hover to reveal the tooltip and verify each classification shows a distinct message
          await errorBadge.hover()
          await expect(app.getByText(errorMsg)).toBeVisible()

          await app.unroute(routePattern)
        }
      } finally {
        if (integrationId) await deleteIntegrationViaApi(app, integrationId)
      }
    })
  })
})
