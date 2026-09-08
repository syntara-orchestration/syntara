/**
 * E2E Test: Credential Deletion with Integration Impact Warning (Test 37)
 *
 * Verifies that deleting a credential used as a management credential by an
 * integration displays a warning listing the affected integrations.
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { deleteIntegrationViaApi } from './seeds/resources'
import { apiRequest, createCredentialViaApi, deleteCredentialViaApi, ensureProject, getAuthToken } from './utils/api'

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
            base_url: `https://example.com`,
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

      // The backend rejects this delete outright while the integration references the
      // credential — the dialog must say so and block confirmation, not just list the
      // integration as an "affected" resource and let the user ack a doomed deletion.
      await expect(
        modal.getByText("This credential can't be deleted until it's detached from these integrations")
      ).toBeVisible({ timeout: 15_000 })
      await expect(modal.getByText(new RegExp(integrationName))).toBeVisible()
      await expect(modal.getByRole('checkbox')).not.toBeVisible()
      await expect(modal.getByRole('button', { name: 'Detach integrations first' })).toBeDisabled()

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

  test('DELETE /credentials/{id} is rejected while an integration still references it', async ({ app }) => {
    // DELETE /credentials/{id} used to succeed silently and null out the
    // integration's management_credential_id. The backend now rejects the delete
    // (409 CREDENTIAL_IN_USE) while any integration still references the credential.
    //
    // The UI disables the delete confirmation entirely in this state (see the
    // previous test), so there's no click-path through the dialog to exercise here.
    // This hits the API directly as a defense-in-depth regression check for the
    // backend contract, independent of the frontend.
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
            base_url: `https://example.com`,
          },
          management_credential_id: credentialId,
          scope: 'global',
        },
      })
      expect(intResp.ok()).toBeTruthy()
      const integration = (await intResp.json()) as { id: string }
      integrationId = integration.id

      const deleteResp = await apiRequest(app, 'delete', `/credentials/${credentialId}`, {
        token: token ?? undefined,
      })
      expect(deleteResp.status()).toBe(409)
      const body = (await deleteResp.json()) as { code?: string; detail?: string }
      expect(body.code).toBe('CREDENTIAL_IN_USE')
      expect(body.detail).toContain(integrationName)

      // Both the credential and the integration's link to it remain intact.
      const detailResp = await apiRequest(app, 'get', `/integrations/${integrationId}`, { token: token ?? undefined })
      expect(detailResp.ok()).toBeTruthy()
      const detail = (await detailResp.json()) as { management_credential_id: string | null }
      expect(detail.management_credential_id).toBe(credentialId)
    } finally {
      // Detach before cleanup: the credential can't be deleted while the
      // integration still references it.
      if (integrationId) await deleteIntegrationViaApi(app, integrationId)
      if (credentialId) await deleteCredentialViaApi(app, credentialId)
    }
  })
})
