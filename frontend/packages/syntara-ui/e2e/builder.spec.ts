import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi } from './helpers/workflows'

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
