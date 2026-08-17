/**
 * E2E Test: Credential Deletion with Integration Impact Warning (Test 37)
 *
 * Verifies that deleting a credential used as a management credential by an
 * integration displays a warning listing the affected integrations.
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { deleteIntegrationViaApi } from './seeds/resources'
import { apiRequest, createCredentialViaApi, deleteCredentialViaApi, ensureProject, getAuthToken } from './utils/api'

// Real backend rejects an unresolvable base_url as an SSRF risk; use the compose-allowlisted
// mcp-server host (override via SYNTARA_E2E_INTEGRATION_HOST). Mock mode keeps a readable placeholder.
const isRealBackend = isSkipWebServerForPlaywrightTests()
const ssrfSafeIntegrationHost = process.env.SYNTARA_E2E_INTEGRATION_HOST ?? 'https://mcp-server'

test.describe('Credential Delete — Integration Impact Warning', () => {
  test('delete credential dialog warns about affected integrations', async ({ app }) => {
    const credName = buildUniqueName('e2e-cred-t37')
    const integrationName = buildUniqueName('e2e-int-t37')
    let credentialId: string | undefined
    let integrationId: string | undefined

    try {
      const token = await getAuthToken(app)
      const project = await ensureProject(app)
      expect(project).not.toBeNull()

      // Create a credential
      credentialId = (await createCredentialViaApi(app, { name: credName, projectId: project!.id })) ?? undefined
      expect(credentialId).toBeDefined()

      // Create an integration linked to the credential via management_credential_id
      const intResp = await apiRequest(app, 'post', '/integrations', {
        token: token ?? undefined,
        data: {
          name: integrationName,
          integration_type: 'mcp_server',
          configuration: {
            integration_type: 'mcp_server',
            base_url: isRealBackend ? ssrfSafeIntegrationHost : `https://${integrationName}.example.com`,
          },
          management_credential_id: credentialId,
          scope: 'global',
        },
      })
      expect(intResp.ok()).toBeTruthy()
      const integration = (await intResp.json()) as { id: string }
      integrationId = integration.id

      // Navigate to credentials list
      await app.goto(toAppUrl('/configuration/credentials'))
      await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible({ timeout: 20_000 })

      // Filter to find the credential
      await app.getByPlaceholder('Filter by keyword').fill(credName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await expect(row).toBeVisible({ timeout: 30_000 })

      // Open kebab menu and click Delete
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: /Delete credential/i }).click()

      // Verify the delete dialog shows the integration warning
      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()
      await expect(modal.getByText('Delete credential?')).toBeVisible()

      // Ripple-effect summary: header, named integration, and ack copy
      await expect(modal.getByText('Resources that will be affected')).toBeVisible({ timeout: 15_000 })
      await expect(modal.getByText('Integrations')).toBeVisible()
      await expect(modal.getByText(new RegExp(integrationName))).toBeVisible()
      await expect(
        modal.getByRole('checkbox', {
          name: 'I understand this credential and the resources shown above will be affected by this deletion.',
        })
      ).toBeVisible()

      // Cancel to leave both credential and integration intact
      await modal.getByRole('button', { name: 'Cancel' }).click()
      await expect(modal).not.toBeVisible()

      // Verify credential still exists in the list
      await expect(row).toBeVisible()
    } finally {
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })

  test('deleting a linked credential removes it and clears the integration credential field', async ({ app }) => {
    const credName = buildUniqueName('e2e-cred-t37-del')
    const integrationName = buildUniqueName('e2e-int-t37-del')
    let credentialId: string | undefined
    let integrationId: string | undefined

    try {
      const token = await getAuthToken(app)
      const project = await ensureProject(app)
      expect(project).not.toBeNull()

      credentialId = (await createCredentialViaApi(app, { name: credName, projectId: project!.id })) ?? undefined
      expect(credentialId).toBeDefined()

      const intResp = await apiRequest(app, 'post', '/integrations', {
        token: token ?? undefined,
        data: {
          name: integrationName,
          integration_type: 'mcp_server',
          configuration: {
            integration_type: 'mcp_server',
            base_url: isRealBackend ? ssrfSafeIntegrationHost : `https://${integrationName}.example.com`,
          },
          management_credential_id: credentialId,
          scope: 'global',
        },
      })
      expect(intResp.ok()).toBeTruthy()
      const integration = (await intResp.json()) as { id: string }
      integrationId = integration.id

      await app.goto(toAppUrl('/configuration/credentials'))
      await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible({ timeout: 20_000 })

      await app.getByPlaceholder('Filter by keyword').fill(credName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(credName) })
      await expect(row).toBeVisible({ timeout: 30_000 })

      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: /Delete credential/i }).click()

      const modal = app.getByRole('dialog')
      await expect(modal).toBeVisible()
      await expect(modal.getByText(new RegExp(integrationName))).toBeVisible({ timeout: 15_000 })

      await modal.getByRole('checkbox').click()
      await modal.getByRole('button', { name: 'Delete' }).click()

      await expect(app.getByText('Credential deleted')).toBeVisible({ timeout: 10_000 })
      await expect(row).not.toBeVisible({ timeout: 10_000 })

      credentialId = undefined
    } finally {
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })
})
