/**
 * E2E Tests: Configure Execution Target create form
 *
 * Critical paths covered:
 * - List toolbar CTA opens the create form with the readonly OpenShift cluster
 * - Valid submit POSTs, shows success toast, and lands on the new detail page
 * - Invalid namespace blocks submit with a field error
 * - Duplicate name keeps values and surfaces a configure failure
 * - Dirty Cancel prompts the unsaved-changes guard before leaving
 *
 * Edge cases:
 * - Cleanup deletes the created target via the execution-plane facade DELETE
 * - Skipped when Execution Plane API is unreachable (compose CI does not start it)
 * - Create/cluster assertions skipped without exactly one OpenShift integration
 */
import { test, expect, toAppUrl, appBaseUrl, type Page } from './fixtures'
import { hasSingleOpenShiftIntegration, isExecutionPlaneListReachable } from './helpers/execution-plane'
import { buildUniqueName } from './helpers/workflows'
import { getAuthToken } from './utils/api'

const LIST_URL = '/execution-plane'
const CREATE_URL = '/execution-plane/create'
const SEEDED_TARGET_NAME = 'Prod OpenShift West'

async function deleteExecutionTarget(app: Page, targetId: string): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) return

  const url = new URL(`/api/execution_plane/v1/execution_targets/${targetId}`, appBaseUrl).toString()
  await app.request.delete(url, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
}

async function openCreateForm(app: Page): Promise<void> {
  await app.goto(toAppUrl(LIST_URL))
  await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
  await app.getByRole('button', { name: 'Configure execution target' }).click()
  await expect(app).toHaveURL(new RegExp(`${CREATE_URL}$`))
  await expect(app.getByRole('heading', { level: 1, name: 'Configure execution target' })).toBeVisible()
}

test.describe('Execution Plane — configure execution target', { tag: '@pr-check' }, () => {
  test.beforeEach(async ({ app }) => {
    test.skip(
      !(await isExecutionPlaneListReachable(app)),
      'Execution Plane API is not available in this environment (compose CI does not start execution-plane-api)'
    )
  })

  test('toolbar CTA opens create form with readonly OpenShift cluster', async ({ app }) => {
    test.skip(!(await hasSingleOpenShiftIntegration(app)), 'Requires exactly one OpenShift integration')

    await openCreateForm(app)

    await expect(app.getByRole('textbox', { name: 'Execution target name' })).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Execution namespace' })).toBeVisible()
    await expect(app.getByText('prod-openshift-west')).toBeVisible()
  })

  test('submits a valid target and navigates to detail', async ({ app }) => {
    test.skip(!(await hasSingleOpenShiftIntegration(app)), 'Requires exactly one OpenShift integration')

    const name = buildUniqueName('e2e-et')
    let createdId: string | null = null

    try {
      await openCreateForm(app)

      await app.getByRole('textbox', { name: 'Execution target name' }).fill(name)
      await app.getByRole('textbox', { name: 'Execution namespace' }).fill('aao-execution')
      await app.getByRole('textbox', { name: 'Node selector key 1' }).fill('region')
      await app.getByRole('textbox', { name: 'Node selector value 1' }).fill('us-east')

      // Capture id from the create response before UI assertions so cleanup still runs if they flake.
      const createResponse = app.waitForResponse(
        (res) =>
          res.request().method() === 'POST' &&
          res.url().includes('/api/execution_plane/v1/execution_targets') &&
          res.status() === 201
      )
      await app.getByRole('button', { name: 'Configure execution target' }).click()
      const body = (await (await createResponse).json()) as { id?: string }
      createdId = body.id ?? null
      expect(createdId, 'expected create response to include an execution target id').toBeTruthy()

      await expect(app.getByText('Execution target configured')).toBeVisible()
      await expect(app.getByRole('heading', { level: 1, name })).toBeVisible()
      await expect(app).toHaveURL(new RegExp(`/execution-plane/${createdId}$`))
    } finally {
      if (createdId) await deleteExecutionTarget(app, createdId)
    }
  })

  test('blocks submit when namespace format is invalid', async ({ app }) => {
    await openCreateForm(app)

    await app.getByRole('textbox', { name: 'Execution target name' }).fill(buildUniqueName('e2e-et-ns'))
    await app.getByRole('textbox', { name: 'Execution namespace' }).fill('Invalid_Namespace')
    await app.getByRole('button', { name: 'Configure execution target' }).click()

    await expect(app.getByText(/invalid namespace format/i)).toBeVisible()
    await expect(app).toHaveURL(new RegExp(`${CREATE_URL}$`))
  })

  test('keeps form values when create fails with a duplicate name', async ({ app }) => {
    test.skip(!(await hasSingleOpenShiftIntegration(app)), 'Requires exactly one OpenShift integration')

    await openCreateForm(app)

    await app.getByRole('textbox', { name: 'Execution target name' }).fill(SEEDED_TARGET_NAME)
    await app.getByRole('textbox', { name: 'Execution namespace' }).fill('aao-execution')
    await app.getByRole('button', { name: 'Configure execution target' }).click()

    await expect(app.getByText(/failed to configure execution target/i)).toBeVisible()
    await expect(app.getByRole('textbox', { name: 'Execution target name' })).toHaveValue(SEEDED_TARGET_NAME)
    await expect(app.getByRole('textbox', { name: 'Execution namespace' })).toHaveValue('aao-execution')
    await expect(app).toHaveURL(new RegExp(`${CREATE_URL}$`))
  })

  test('prompts to discard unsaved changes when Cancel is clicked', async ({ app }) => {
    await openCreateForm(app)

    await app.getByRole('textbox', { name: 'Execution target name' }).fill(buildUniqueName('e2e-et-dirty'))
    await app.getByRole('button', { name: 'Cancel' }).click()

    const dialog = app.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Discard unsaved changes?')).toBeVisible()

    await dialog.getByRole('button', { name: 'Exit without saving' }).click()
    await expect(app).toHaveURL(new RegExp(`${LIST_URL}$`))
    await expect(app.getByRole('heading', { level: 1, name: 'Execution Plane' })).toBeVisible()
  })
})
