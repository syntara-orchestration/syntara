/**
 * E2E Tests: Default Builtin Groups — Visibility
 *
 * Reference: UI-31, AAP-73926 (AAP-73926)
 */
import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { apiRequest, createGroupViaApi, deleteGroupViaApi, findBuiltinGroupByName, getAuthToken } from './utils/api'

const GROUPS_URL = '/system-administration/access-management/groups'

test.describe('UI-31: Default Builtin Groups — Visibility', () => {
  let groupsTable: ReturnType<Page['getByRole']>

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(GROUPS_URL))
    await expect(app.getByRole('heading', { level: 1, name: /access management/i })).toBeVisible()

    groupsTable = app.getByRole('grid', { name: /Groups table/i })
    await expect(groupsTable).toBeVisible()
  })

  test('builtin Auditors and Users groups are visible in the groups list', async ({ app }) => {
    const auditorsRow = groupsTable.getByRole('row', { name: /auditors/i })
    const usersRow = groupsTable.getByRole('row').filter({ has: app.getByRole('button', { name: 'users' }) })

    await expect(auditorsRow).toBeVisible()
    await expect(usersRow).toBeVisible()
  })

  test('builtin groups cannot be deleted via the API', async ({ app }) => {
    const auditors = await findBuiltinGroupByName(app, 'auditors')
    const users = await findBuiltinGroupByName(app, 'users')

    if (!auditors?.id || !users?.id) {
      throw new Error('Expected builtin auditors and users groups from the API')
    }

    const token = await getAuthToken(app)
    if (!token) {
      throw new Error('SYNTARA_E2E_PASSWORD is required for API assertions')
    }

    for (const groupId of [auditors.id, users.id]) {
      const resp = await apiRequest(app, 'delete', `/groups/${groupId}`, { token })
      expect(resp.status()).toBe(403)
    }
  })

  test('builtin groups have no row actions; non-builtin groups do', async ({ app }) => {
    const groupName = buildUniqueName('e2e-ui31-actions')
    const groupId = await createGroupViaApi(app, { name: groupName })
    if (!groupId) {
      throw new Error('Failed to create non-builtin group via API')
    }

    try {
      const auditorsRow = groupsTable.getByRole('row', { name: /auditors/i })
      const usersRow = groupsTable.getByRole('row').filter({ has: app.getByRole('button', { name: 'users' }) })

      await expect(auditorsRow).toBeVisible()
      await expect(usersRow).toBeVisible()
      await expect(auditorsRow.getByRole('button', { name: /Actions|Kebab toggle/i })).not.toBeVisible()
      await expect(usersRow.getByRole('button', { name: /Actions|Kebab toggle/i })).not.toBeVisible()

      await app.getByRole('textbox', { name: /name filter/i }).fill(groupName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const customRow = groupsTable.getByRole('row', { name: new RegExp(groupName) })
      await expect(customRow).toBeVisible()
      await expect(customRow.getByRole('button', { name: /Kebab toggle/i })).toBeVisible()
    } finally {
      await deleteGroupViaApi(app, groupId)
    }
  })
})
