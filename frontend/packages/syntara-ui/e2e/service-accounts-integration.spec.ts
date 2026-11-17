/**
 * E2E Tests: Service Accounts — Integration (Authenticated Read, Admin Management)
 *
 * Test cases covered:
 * - Authenticated users create and read identities regardless of creator or project role
 * - Project admins cannot update or disable service accounts
 */
import { test, expect } from './fixtures'
import {
  goToServiceAccountsList,
  filterServiceAccountByName,
  goToServiceAccountDetail,
  deleteServiceAccountViaApi,
} from './helpers/service-accounts'
import { buildUniqueName } from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { apiRequest } from './utils/api'

const isRealBackend = isSkipWebServerForPlaywrightTests()

test.describe('Service account access', () => {
  test.skip(isRealBackend, 'project-admin is a mock-only role with no real backend equivalent')
  test('project admin sees accounts created by other users', async ({ app, projectAdminApp }) => {
    const otherUserSaName = buildUniqueName('sa-other-user')
    const projectAdminSaName = buildUniqueName('sa-project-admin')
    let otherSaId: string | undefined
    let ownSaId: string | undefined

    try {
      // Another human creates an account.

      const otherResp = await apiRequest(app, 'post', '/service_accounts', {
        data: { name: otherUserSaName, description: 'Unrelated identity' },
      })
      const otherSa = (await otherResp.json()) as { id: string }
      otherSaId = otherSa.id

      // The current human creates an account.

      const ownResp = await apiRequest(projectAdminApp, 'post', '/service_accounts', {
        token: 'mock-token-project-admin',
        data: { name: projectAdminSaName, description: 'Created by a project admin' },
      })
      const ownSa = (await ownResp.json()) as { id: string }
      ownSaId = ownSa.id

      // Project admin navigates to SA list
      await goToServiceAccountsList(projectAdminApp)

      await filterServiceAccountByName(projectAdminApp, projectAdminSaName)
      await expect(projectAdminApp.getByRole('row', { name: new RegExp(projectAdminSaName) })).toBeVisible()

      // Any authenticated user can read accounts created by another user.
      await projectAdminApp.getByRole('button', { name: 'Reset' }).click()
      await filterServiceAccountByName(projectAdminApp, otherUserSaName)
      await expect(projectAdminApp.getByRole('row', { name: new RegExp(otherUserSaName) })).toBeVisible()
    } finally {
      if (ownSaId) await deleteServiceAccountViaApi(app, ownSaId)
      if (otherSaId) await deleteServiceAccountViaApi(app, otherSaId)
    }
  })

  test('project admin has create permission and can view created SAs', async ({ app, projectAdminApp }) => {
    const saName = buildUniqueName('sa-pa-create')
    let saId: string | undefined

    try {
      // Verify the create button is enabled (not permission-gated) for project-admin
      await goToServiceAccountsList(projectAdminApp)
      const createButton = projectAdminApp.getByRole('button', { name: 'Create service account' })
      await expect(createButton).toBeVisible()
      await expect(createButton).not.toHaveAttribute('aria-disabled', 'true')

      // Create with the same signed-in user who will manage the account.

      const resp = await apiRequest(projectAdminApp, 'post', '/service_accounts', {
        token: 'mock-token-project-admin',
        data: { name: saName, description: 'Created for project-admin' },
      })
      const sa = (await resp.json()) as { id: string }
      saId = sa.id

      // Project admin can see the SA in their filtered list
      await projectAdminApp.reload()
      await filterServiceAccountByName(projectAdminApp, saName)
      await expect(projectAdminApp.getByRole('row', { name: new RegExp(saName) })).toBeVisible()
    } finally {
      if (saId) await deleteServiceAccountViaApi(app, saId)
    }
  })

  test('project admin cannot edit a service account', async ({ app, projectAdminApp }) => {
    const originalName = buildUniqueName('sa-pa-edit')
    let saId: string | undefined

    try {
      const resp = await apiRequest(projectAdminApp, 'post', '/service_accounts', {
        token: 'mock-token-project-admin',
        data: { name: originalName, description: 'SA for edit test' },
      })
      const sa = (await resp.json()) as { id: string; name: string }
      saId = sa.id

      // Project admin navigates to the SA detail page
      await goToServiceAccountDetail(projectAdminApp, { id: sa.id, name: originalName })

      const editButton = projectAdminApp.getByRole('button', { name: 'Edit service account' })
      await expect(editButton).toHaveAttribute('aria-disabled', 'true')
      await expect(projectAdminApp.getByRole('dialog')).not.toBeVisible()
    } finally {
      if (saId) await deleteServiceAccountViaApi(app, saId)
    }
  })

  test('project admin cannot disable a service account', async ({ app, projectAdminApp }) => {
    const saName = buildUniqueName('sa-pa-disable')
    let saId: string | undefined

    try {
      const resp = await apiRequest(projectAdminApp, 'post', '/service_accounts', {
        token: 'mock-token-project-admin',
        data: { name: saName, description: 'SA for disable test' },
      })
      const sa = (await resp.json()) as { id: string; name: string }
      saId = sa.id

      // Project admin navigates to the SA detail page
      await goToServiceAccountDetail(projectAdminApp, { id: sa.id, name: saName })

      const toggle = projectAdminApp.getByRole('switch', { name: 'Toggle service account status' })
      await expect(toggle).toBeDisabled()
      await expect(toggle).toBeChecked()
    } finally {
      if (saId) await deleteServiceAccountViaApi(app, saId)
    }
  })
})
