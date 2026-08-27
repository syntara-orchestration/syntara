import { test, expect, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow } from './helpers/workflows'

test('workflows page toolbar shows Import workflow before Create workflow', async ({ app }) => {
  await app.goto(toAppUrl('/workflows'))
  await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

  const createButton = app.getByRole('button', { name: 'Create workflow' })
  const importButton = app.getByRole('button', { name: 'Import workflow' })

  await expect(createButton).toBeVisible()
  await expect(importButton).toBeVisible()

  // Import (secondary) appears to the left of Create (primary) per PF convention
  const importBox = await importButton.boundingBox()
  const createBox = await createButton.boundingBox()
  expect(importBox?.x).toBeLessThan(createBox?.x ?? Infinity)
})

test('workflows table renders data rows', async ({ app }) => {
  await app.goto(toAppUrl('/workflows'))
  await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
  await expect(app).toHaveTitle(`Workflows | ${APP_TITLE}`)
  const workflowsTable = app.getByRole('grid', { name: 'Workflows table' })
  await expect(workflowsTable).toBeVisible()
  const pagination = app.getByText(/\d+\s*-\s*\d+\s+of\s+(\d+)/)
  await expect(pagination).toBeVisible()
  const total = Number((await pagination.textContent())?.match(/of\s+(\d+)/)?.[1] ?? '0')
  test.skip(total === 0, 'No workflows in table to assert row visibility')
  // Kebab aria-label is stable when row accessible names are not (grouped table + Truncate).
  // PatternFly expandable tables wrap each row in its own tbody, so positional
  // selectors like "tbody tr:first-child" match multiple elements. Filter to
  // visible elements (`:visible`) and assert at least one is present — this is
  // stronger than not.toHaveCount(0) which only checks DOM presence.
  await expect(workflowsTable.getByLabel(/^Actions for /).locator(':visible')).not.toHaveCount(0)
})

test('user searches, views, and deletes a workflow', async ({ app }) => {
  test.setTimeout(90_000)
  // Arrange - Create a workflow to manage
  const workflowName = buildUniqueName('e2e-workflow')
  const otherWorkflowName = buildUniqueName('e2e-workflow-control')

  try {
    await createBasicWorkflowViaApi(app, workflowName, 'Manage workflow')
    await createBasicWorkflowViaApi(app, otherWorkflowName, 'Control workflow')
    // Act - Filter for the target workflow by its unique suffix
    await app.goto(toAppUrl('/workflows'))
    const searchTerm = workflowName.slice(-6)
    await app.getByPlaceholder('Filter by name').fill(searchTerm)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const targetRow = app.getByRole('row', { name: new RegExp(workflowName) })
    await expect(targetRow).toBeVisible()

    // Act - View details via the workflow button
    await targetRow.getByRole('link', { name: workflowName, exact: true }).click()

    // Assert - Builder shows the expected workflow
    await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)

    // Act - Delete the workflow from the list
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(searchTerm)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const deleteRow = app.getByRole('row', { name: new RegExp(workflowName) })
    await expect(deleteRow).toBeVisible()
    await deleteRow.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
    await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
    await app.getByRole('checkbox', { name: /I understand this workflow/i }).check()
    await app.getByRole('button', { name: 'Delete' }).click()

    // Assert - Workflow no longer appears
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(app.getByRole('row', { name: new RegExp(workflowName) })).toHaveCount(0)
  } finally {
    for (const name of [otherWorkflowName, workflowName]) {
      await deleteWorkflow(app, name)
    }
  }
})
