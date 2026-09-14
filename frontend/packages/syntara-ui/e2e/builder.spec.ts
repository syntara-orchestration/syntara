import { test, expect, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import {
  buildUniqueName,
  clickAddConnectedStep,
  closeNodeEditorPanel,
  createBasicWorkflowViaApi,
  fillCodeEditor,
  selectProjectIfRequired,
} from './helpers/workflows'

test('user creates and saves a multi-node workflow', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-multi-node')
  await app.goto(toAppUrl('/workflow-builder/new'))
  await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()
  await expect(app).toHaveTitle(`New Workflow | Workflows | ${APP_TITLE}`)

  try {
    // Act - Add manual trigger
    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    // Act - Add connected action node
    const firstPanel = await clickAddConnectedStep(app)
    await firstPanel.getByRole('button', { name: 'Action', exact: true }).click()
    await firstPanel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Send email')
    await fillCodeEditor(app, { value: 'print("hello from Playwright")' })
    await app.getByRole('button', { name: 'Create' }).click()
    await closeNodeEditorPanel(app)

    // Act - Add another connected action node
    const secondPanel = await clickAddConnectedStep(app)
    await secondPanel.getByRole('button', { name: 'Action', exact: true }).click()
    await secondPanel.getByRole('button', { name: 'Script', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Follow-up action')
    await fillCodeEditor(app, { value: 'print("follow-up")' })
    await app.getByRole('button', { name: 'Create' }).click()

    // Act - Save workflow (select project first to avoid name reset)
    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()

    // Assert - Workflow is persisted in workflows list
    await expect(app).toHaveURL(/workflow-builder\/.+/)
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(app.getByRole('link', { name: workflowName, exact: true })).toBeVisible()
  } finally {
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const row = app.getByRole('row', { name: new RegExp(workflowName) })
    if ((await row.count()) > 0) {
      await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
      await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
      await app.getByRole('checkbox', { name: /I understand this workflow/i }).check()
      await app.getByRole('button', { name: 'Delete' }).click()
    }
  }
})

test('user edits an existing workflow and changes persist', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-edit')
  await createBasicWorkflowViaApi(app, workflowName, 'Initial task')

  const updatedName = `${workflowName}-updated`

  try {
    // Act - Open workflow from workflows list
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('link', { name: workflowName, exact: true }).click()

    await app.getByPlaceholder('Workflow name').fill(updatedName)
    await app.getByRole('button', { name: 'Save' }).click()

    // Assert - Updated name persists
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(updatedName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(app.getByRole('link', { name: updatedName, exact: true })).toBeVisible()
  } finally {
    for (const name of [updatedName, workflowName]) {
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(name)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const row = app.getByRole('row', { name: new RegExp(name) })
      if ((await row.count()) > 0) {
        await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click({ force: true })
        await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
        await app.getByRole('checkbox', { name: /I understand this workflow/i }).check()
        await app.getByRole('button', { name: 'Delete' }).click()
      }
    }
  }
})
