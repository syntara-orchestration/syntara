/**
 * E2E Tests: Credential Username Links
 *
 * Verifies that created_by and updated_by usernames in the credentials
 * list and detail pages render as navigable links to user detail pages.
 *
 * Critical paths covered:
 * - Credential list: Created column username is a link to user detail
 * - Credential detail: Created/Last modified usernames are links
 * - Links point to the correct user detail URL (/system-administration/access-management/users/:id)
 */
import { test, expect, toAppUrl } from './fixtures'
import { filterCredentialByName, goToCredentialsList } from './helpers/credentials'
import { buildUniqueName } from './helpers/workflows'
import { createCredentialSeed, deleteCredentialViaApi, type SeededCredential } from './seeds/resources'
import { getAuthToken } from './utils/api'

const USER_DETAIL_HREF_PATTERN = /^\/system-administration\/access-management\/users\/[a-f0-9-]+$/

let seededCred: SeededCredential | null = null
let credName: string

test.beforeAll(async ({ browser }) => {
  credName = buildUniqueName('e2e-userlink')
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (!token) throw new Error('credential-user-links beforeAll: could not obtain auth token')
  seededCred = await createCredentialSeed(page, { name: credName, token })
  await page.close()
})

test.afterAll(async ({ browser }) => {
  if (!seededCred) return
  const page = await browser.newPage()
  await deleteCredentialViaApi(page, seededCred.id)
  await page.close()
})

// Real-backend only: credential seed requires auth token; not tagged @pr-check intentionally
test.describe('Credential Username Links', () => {
  test('credential list shows created_by username as a link to user detail', async ({ app }) => {
    expect(seededCred, 'Credential seed not available').toBeTruthy()

    await goToCredentialsList(app)
    await filterCredentialByName(app, credName)

    const row = app.getByRole('row', { name: new RegExp(credName) })
    await expect(row).toBeVisible()

    const createdCell = row.locator('td[data-label="Created"]')
    const userLink = createdCell.getByRole('link')
    await expect(userLink).toBeVisible()

    const href = await userLink.getAttribute('href')
    expect(href).toMatch(USER_DETAIL_HREF_PATTERN)
  })

  test('credential detail shows Created username as a link to user detail', async ({ app }) => {
    expect(seededCred, 'Credential seed not available').toBeTruthy()
    if (!seededCred) {
      throw new Error('Credential seed not available')
    }

    await app.goto(toAppUrl(`/configuration/credentials/${seededCred.id}`))
    await expect(app.getByRole('heading', { name: credName, level: 1 })).toBeVisible({ timeout: 15_000 })

    const detailsTab = app.getByRole('tabpanel', { name: 'Details' })

    const createdLink = detailsTab.locator('dt', { hasText: 'Created' }).locator('~ dd').getByRole('link')
    await expect(createdLink).toBeVisible()

    const href = await createdLink.getAttribute('href')
    expect(href).toMatch(USER_DETAIL_HREF_PATTERN)

    const lastModLink = detailsTab.locator('dt', { hasText: 'Last modified' }).locator('~ dd').getByRole('link')
    const hasLastModLink = await lastModLink.isVisible().catch(() => false)
    if (hasLastModLink) {
      const lastModHref = await lastModLink.getAttribute('href')
      expect(lastModHref).toMatch(USER_DETAIL_HREF_PATTERN)
    }
  })
})
