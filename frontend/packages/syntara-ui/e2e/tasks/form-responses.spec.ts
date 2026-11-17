/**
 * E2E Tests (UI-8): Tasks — Form responses tab
 *
 * Critical paths covered:
 * - Pending form steps listed on Tasks with filter, sort, pagination, and project scope
 * - UI-8: Row opens execution detail with the form prompt panel
 * - UI-8: Pending form step appears on Tasks after a workflow run (API-created)
 *
 * Mock seed: syntara-mock-api/src/resources/formPrompts.ts
 */
import { createUnavailableGuard, test, expect, toAppUrl } from '../fixtures'
import { APP_TITLE } from '../helpers/appTitle'
import {
  MOCK_FORM_RESPONSE_SEED,
  applyFormResponseNameFilter,
  applyFormResponseStatusFilter,
  createPendingFormPromptLight,
  disposeFormPromptWorkflow,
  isMockFormPromptSidePanelSeedAvailable,
  openFormResponsesTab,
  tasksProjectSelector,
} from '../helpers/formResponses'
import { paginationFooterForTable } from '../helpers/patternfly'
import { buildUniqueName } from '../helpers/workflows'
import { apiRequest, getAuthToken } from '../utils/api'

/** Tests that need multi-row / multi-project mock seeds — do not create API rows in beforeEach. */
const MOCK_SEED_ONLY_TESTS = new Set([
  'filters form responses by name and status',
  'expands a row to show message and submitted data',
  'groups rows by project when All projects is selected',
  'scopes the list to the selected project',
])

test.describe('Tasks — Form responses tab', { tag: '@pr-check' }, () => {
  const seedGuard = createUnavailableGuard(
    'Form responses seed data required (see syntara-mock-api formPrompts or run against a seeded backend)'
  )

  let usingApiRow = false
  let apiRow: { promptName: string; workflowId: string } | undefined

  test.beforeEach(async ({ app }, testInfo) => {
    usingApiRow = false
    apiRow = undefined

    const hasSeed = await isMockFormPromptSidePanelSeedAvailable(app)
    if (!hasSeed && MOCK_SEED_ONLY_TESTS.has(testInfo.title)) {
      test.skip(true, 'Requires mock API form response seed rows')
      return
    }

    if (!hasSeed && !process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']) {
      seedGuard.markUnavailable()
      expect(
        hasSeed,
        'Form responses seed data required (see syntara-mock-api formPrompts or run against a seeded backend)'
      ).toBeTruthy()
      return
    }

    if (!hasSeed) {
      const created = await createPendingFormPromptLight(app, 'e2e-form-responses-tab')
      apiRow = { promptName: created.promptName, workflowId: created.workflowId }
      usingApiRow = true
    }

    const table = await openFormResponsesTab(app)
    if (usingApiRow && apiRow) {
      await applyFormResponseNameFilter(app, table, apiRow.promptName, { waitForRowText: apiRow.promptName })
      return
    }

    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible({
      timeout: 15_000,
    })
  })

  test.afterEach(async ({ app }) => {
    if (apiRow?.workflowId) {
      await disposeFormPromptWorkflow(app, apiRow.workflowId)
      apiRow = undefined
      usingApiRow = false
    }
  })

  test('shows the form responses table with seeded rows', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Form responses table' })
    await expect(app).toHaveTitle(`Tasks | ${APP_TITLE}`)

    if (usingApiRow && apiRow) {
      await expect(table.getByRole('link', { name: apiRow.promptName })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Name' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Workflow' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Initiated' })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: 'Status' })).toBeVisible()
      return
    }

    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible()
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.submittedName })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Name' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Workflow' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Initiated' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Status' })).toBeVisible()
  })

  test('filters form responses by name and status', async ({ app }) => {
    test.skip(usingApiRow, 'Name/status filter matrix requires mock seed rows')
    const table = app.getByRole('grid', { name: 'Form responses table' })

    await applyFormResponseNameFilter(app, table, 'Collect', {
      waitForRowText: MOCK_FORM_RESPONSE_SEED.pendingName,
    })

    const nameChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Name' })
    await expect(nameChipGroup.getByText('Collect')).toBeVisible()
    await expect(app).toHaveURL(/name%5Bcontains%5D=Collect|name\[contains\]=Collect/)

    await applyFormResponseStatusFilter(app, 'Pending')

    const statusChipGroup = app.getByRole('search', { name: 'Filters' }).getByRole('list', { name: 'Status' })
    await expect(statusChipGroup.getByText('Pending')).toBeVisible()
    await expect(app).toHaveURL(/status%5Bin%5D=pending|status\[in\]=pending/)
    await expect(table.getByRole('row').filter({ hasText: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible()
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.submittedName })).not.toBeVisible()

    await app.getByRole('search', { name: 'Filters' }).getByRole('button', { name: 'Clear all filters' }).click()
    await expect(app.getByRole('search', { name: 'Filters' }).getByRole('list')).toHaveCount(0)
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.submittedName })).toBeVisible()
  })

  test('shows empty state when name filter matches nothing', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Form responses table' })
    const impossibleName = buildUniqueName('zzz-nonexistent-form-response')

    await applyFormResponseNameFilter(app, table, impossibleName)

    await expect(app.getByRole('heading', { name: 'No results found' })).toBeVisible()
    await app.getByRole('button', { name: 'Clear all filters' }).last().click()
    const restoredName = usingApiRow && apiRow ? apiRow.promptName : MOCK_FORM_RESPONSE_SEED.pendingName
    await expect(table.getByRole('link', { name: restoredName })).toBeVisible()
  })

  test('sorts by name when the column header is clicked', async ({ app }) => {
    const nameHeader = app.getByRole('columnheader', { name: 'Name' })
    await nameHeader.getByRole('button').click()
    await expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')
    await expect(app).toHaveURL(/sort=name/)

    await nameHeader.getByRole('button').click()
    await expect(nameHeader).toHaveAttribute('aria-sort', 'descending')
    await expect(app).toHaveURL(/sort=-name/)
  })

  test('expands a row to show message and submitted data', async ({ app }) => {
    test.skip(usingApiRow, 'Requires mock seed rows with submitted data')
    const table = app.getByRole('grid', { name: 'Form responses table' })

    const pendingRow = table.getByRole('row').filter({ hasText: MOCK_FORM_RESPONSE_SEED.pendingName })
    await pendingRow.getByRole('button', { name: /details/i }).click()
    await expect(table.getByText(MOCK_FORM_RESPONSE_SEED.pendingMessage)).toBeVisible({ timeout: 15_000 })

    const submittedRow = table.getByRole('row').filter({ hasText: MOCK_FORM_RESPONSE_SEED.submittedName })
    await submittedRow.getByRole('button', { name: /details/i }).click()
    await expect(table.getByText(MOCK_FORM_RESPONSE_SEED.submittedDataSnippet)).toBeVisible({ timeout: 15_000 })
  })

  test('UI-8: opens execution detail with the form prompt panel from the Tasks name link', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Form responses table' })
    const linkName = usingApiRow && apiRow ? apiRow.promptName : MOCK_FORM_RESPONSE_SEED.pendingName

    await table.getByRole('link', { name: linkName }).click()

    if (usingApiRow && apiRow) {
      await expect(app).toHaveURL(/\/executions\/[^/]+\?form_prompt=[^&]+(&history=closed)?/)
    } else {
      await expect(app).toHaveURL(
        new RegExp(
          `/executions/${MOCK_FORM_RESPONSE_SEED.executionId}\\?form_prompt=${MOCK_FORM_RESPONSE_SEED.pendingId}(&history=closed)?`
        )
      )
    }
    await expect(app).toHaveURL(/history=closed/)
    await expect(app.getByRole('heading', { name: 'Respond to prompt' })).toBeVisible({ timeout: 15_000 })
  })

  test('switches between Tasks tabs via URL', async ({ app }) => {
    await app.goto(toAppUrl('/tasks/approvals'))
    await expect(app.getByRole('tab', { name: 'Approvals', selected: true })).toBeVisible()

    await app.getByRole('tab', { name: 'Form responses' }).click()
    await expect(app).toHaveURL(/\/tasks\/form-responses/)
    await expect(app.getByRole('tab', { name: 'Form responses', selected: true })).toBeVisible()
    await expect(app.getByRole('grid', { name: 'Form responses table' })).toBeVisible({ timeout: 15_000 })
  })

  test('groups rows by project when All projects is selected', async ({ app }) => {
    test.skip(usingApiRow, 'Requires mock seed rows in multiple projects')
    const projectInput = tasksProjectSelector(app)
    const selectorVisible = await projectInput
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (!selectorVisible) {
      test.skip(true, 'Project selector not available in this environment')
    }

    await projectInput.click()
    await app.getByRole('option', { name: 'All projects' }).click()

    const table = app.getByRole('grid', { name: 'Form responses table' })
    await expect(table.getByText(MOCK_FORM_RESPONSE_SEED.defaultProjectName, { exact: true })).toBeVisible({
      timeout: 15_000,
    })
    await expect(table.getByText(MOCK_FORM_RESPONSE_SEED.otherProjectName, { exact: true })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('scopes the list to the selected project', async ({ app }) => {
    test.skip(usingApiRow, 'Requires mock seed rows in multiple projects')
    const projectInput = tasksProjectSelector(app)
    const selectorVisible = await projectInput
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (!selectorVisible) {
      test.skip(true, 'Project selector not available in this environment')
    }

    const table = app.getByRole('grid', { name: 'Form responses table' })
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible()

    await projectInput.click()
    await app.getByRole('option', { name: MOCK_FORM_RESPONSE_SEED.otherProjectName }).click()

    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).not.toBeVisible({
      timeout: 15_000,
    })
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.otherProjectPendingName })).toBeVisible({
      timeout: 15_000,
    })

    await tasksProjectSelector(app).click()
    await app.getByRole('option', { name: MOCK_FORM_RESPONSE_SEED.defaultProjectName }).click()
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible({
      timeout: 15_000,
    })
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.otherProjectPendingName })).not.toBeVisible({
      timeout: 15_000,
    })
  })
})

test.describe('Tasks — Form responses pagination', { tag: '@pr-check' }, () => {
  const paginationGuard = createUnavailableGuard('Not enough form responses to paginate')

  test.beforeEach(async ({ app }) => {
    await openFormResponsesTab(app)
    const hasSeed = await isMockFormPromptSidePanelSeedAvailable(app)
    if (!hasSeed) {
      paginationGuard.markUnavailable()
      test.skip(true, 'Form responses pagination requires mock API seed rows')
      return
    }
    const table = app.getByRole('grid', { name: 'Form responses table' })
    await expect(table.getByRole('link', { name: MOCK_FORM_RESPONSE_SEED.pendingName })).toBeVisible({
      timeout: 15_000,
    })

    const footer = paginationFooterForTable(app, 'Form responses table')
    const perPageToggle = footer.getByRole('button', { name: /\d+ - \d+/ })
    await perPageToggle.waitFor({ state: 'visible', timeout: 10_000 })
    await perPageToggle.click()
    await app.getByRole('menuitem', { name: /10 per page/i }).click()

    const nextButton = app.getByRole('button', { name: 'Go to next page' })
    const hasNextPage = await nextButton
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => nextButton.isEnabled())
      .catch(() => false)
    if (!hasNextPage) {
      paginationGuard.markUnavailable()
      test.skip(true, 'Need more than ten form responses to paginate (mock pagination seeds)')
    }
  })

  test('next page shows a different form response row', async ({ app }) => {
    const table = app.getByRole('grid', { name: 'Form responses table' })
    const nameLinks = table.getByRole('link')
    const firstPageNames = await nameLinks.allTextContents()

    await app.getByRole('button', { name: 'Go to next page' }).click()

    await expect(async () => {
      const secondPageNames = await nameLinks.allTextContents()
      expect(secondPageNames).not.toEqual(firstPageNames)
    }).toPass({ timeout: 10_000 })
  })
})

test.describe('Tasks — Form responses (API-created)', { tag: '@pr-check' }, () => {
  test('UI-8: lists a pending form step on Tasks after workflow run', async ({ app }) => {
    let workflowId: string | undefined
    let executionId: string | undefined

    try {
      const created = await createPendingFormPromptLight(app, 'e2e-list')
      workflowId = created.workflowId
      executionId = created.executionId

      const table = await openFormResponsesTab(app)
      await applyFormResponseNameFilter(app, table, created.promptName, {
        waitForRowText: created.promptName,
      })
      await expect(table.getByRole('link', { name: created.promptName, exact: true })).toBeVisible()
      await expect(table.getByRole('link', { name: created.workflowName, exact: true })).toBeVisible()
    } finally {
      if (workflowId && executionId) {
        await disposeFormPromptWorkflow(app, workflowId, executionId)
      }
    }
  })

  test('paused form step run is not treated as pending approval', async ({ app }) => {
    let workflowId: string | undefined
    let executionId: string | undefined

    try {
      const created = await createPendingFormPromptLight(app, 'e2e-no-approval-badge')
      workflowId = created.workflowId
      executionId = created.executionId

      const token = (await getAuthToken(app)) ?? undefined
      const resp = await apiRequest(app, 'get', `/executions/${executionId}`, { token })
      const execution = (await resp.json()) as { approval_pending?: boolean }
      expect(execution.approval_pending).toBeFalsy()

      await app.goto(toAppUrl(`/executions/${executionId}`))
      await expect(app.getByTestId('page-header').getByText('Pending approval')).not.toBeVisible()
    } finally {
      if (workflowId && executionId) {
        await disposeFormPromptWorkflow(app, workflowId, executionId)
      }
    }
  })
})
