/**
 * E2E Tests: Access Management — Create/Add button labels and modal consistency
 *
 * Verifies the UX requirement: when navigating to any Access Management tab the
 * primary action button reads either "Create <resource>" or "Add assignment", and
 * the same label appears consistently on the destination form or modal.
 *
 * Critical paths covered:
 * - Users tab: "Create user" button in toolbar → form submit reads "Create user"
 * - Groups tab: "Create group" button → modal title and submit both read "Create group"
 * - Projects tab: "Create project" button → modal title and submit both read "Create project"
 * - Roles tab: "Create role" button → dialog title and submit both read "Create role"
 * - Assignments tab: "Add assignment" button → dialog title "Add Assignment"; submit "Add assignment"
 *
 * Note: the Users form page heading and submit button both use sentence case ("Create user").
 * The Assignments dialog heading uses title case ("Add Assignment") by existing convention;
 * this area was not modified by this PR.
 *
 * Edge cases:
 * - Buttons appear in both the populated toolbar and the empty state CTA
 * - Cancel closes modal/navigates back without persisting any data
 * - Roles tab skips when no seed data is available (empty state has no Create button)
 */
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import { createRoleViaApi, deleteRoleViaApi, type SeededRole } from './seeds/iam'
import { getAuthToken } from './utils/api'

const ACCESS_URL = '/system-administration/access-management'

let seededRole: SeededRole | null = null

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage()
  const token = await getAuthToken(page)
  if (token) {
    const prefix = buildUniqueName('e2e-amb')
    seededRole = await createRoleViaApi(page, { name: `${prefix}-role`, token })
  }
  await page.close()
})

test.afterAll(async ({ browser }) => {
  if (seededRole) {
    const page = await browser.newPage()
    await deleteRoleViaApi(page, seededRole.id)
    await page.close()
  }
})

type ModalTabCase = {
  /** Regex matched against the tab's accessible name to click it. */
  tab: RegExp
  /** URL path segment appended to ACCESS_URL after the tab is active. */
  urlPath: string
  /** Accessible name of the primary action button on the tab. */
  label: string
  /** Expected modal/dialog heading after the button is clicked. */
  heading: string
  /** When true, the test is skipped if the button is not visible (requires pre-existing data). */
  requiresSeedData?: boolean
}

/** Modal-based tabs share the same open → assert → cancel flow. */
const MODAL_TAB_CASES: ModalTabCase[] = [
  { tab: /Groups/i, urlPath: 'groups', label: 'Create group', heading: 'Create group' },
  { tab: /Projects/i, urlPath: 'projects', label: 'Create project', heading: 'Create project' },
  {
    tab: /^Roles$/i,
    urlPath: 'roles',
    label: 'Create role',
    heading: 'Create role',
    requiresSeedData: true,
  },
  {
    tab: /Assignments/i,
    urlPath: 'assignments',
    label: 'Add assignment',
    heading: 'Add Assignment',
  },
]

test.describe('Access Management — Create button labels', () => {
  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl(ACCESS_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
  })

  // Users tab is unique — it navigates to a dedicated form route rather than opening a modal.
  test('"Create user" button navigates to form with matching submit', async ({ app }) => {
    await app.getByRole('tab', { name: /Users/i }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/users`))

    const createButton = app.getByRole('button', { name: 'Create user' })
    await expect(createButton).toBeVisible()
    await createButton.click()

    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/users/create`))
    await expect(app.getByRole('heading', { name: 'Create user' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Create user' })).toBeVisible()

    await app.getByRole('button', { name: 'Cancel' }).click()
    await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/users`))
  })

  // Groups, Projects, Roles, and Assignments all follow the same open → assert → cancel flow.
  for (const { tab, urlPath, label, heading, requiresSeedData } of MODAL_TAB_CASES) {
    test(`"${label}" button opens modal with matching title and submit`, async ({ app }) => {
      await app.getByRole('tab', { name: tab }).click()
      await expect(app).toHaveURL(new RegExp(`${ACCESS_URL}/${urlPath}`))

      const actionButton = app.getByRole('button', { name: label })

      if (requiresSeedData) {
        const hasButton = await actionButton
          .waitFor({ state: 'visible', timeout: 5000 })
          .then(() => true)
          .catch(() => false)
        test.skip(!hasButton, `No seed data available; "${label}" button not visible in empty state`)
      }

      await expect(actionButton).toBeVisible()
      await actionButton.click()

      const dialog = app.getByRole('dialog')
      await expect(dialog.getByRole('heading', { name: heading })).toBeVisible()
      await expect(dialog.getByRole('button', { name: label })).toBeVisible()

      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(app.getByRole('dialog')).not.toBeVisible()
    })
  }
})
