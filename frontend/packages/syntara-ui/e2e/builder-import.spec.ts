import { writeFileSync, unlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, join } from 'node:path'

import { test, expect } from './fixtures'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  deleteWorkflow,
  openWorkflowInBuilder,
  startWorkflowWithTrigger,
} from './helpers/workflows'

function createImportFile(name: string): string {
  const definition = {
    schema_version: '2.0.0',
    name,
    description: 'Imported workflow description',
    triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    nodes: [
      {
        id: 'node_1',
        type: 'script',
        name: 'Imported step',
        parameters: { language: 'python', code: 'print("imported")' },
      },
    ],
    edges: [{ from: 'trigger_1', to: 'node_1' }],
  }
  const filePath = join(tmpdir(), `${basename(name)}.json`)
  writeFileSync(filePath, JSON.stringify(definition))
  return filePath
}

test.skip('builder import shows confirmation modal for existing workflow', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-import-confirm')
  const importName = buildUniqueName('e2e-imported')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Original action')
  const importFile = createImportFile(importName)

  try {
    await openWorkflowInBuilder(app, workflowName, id)

    const kebab = app.getByRole('button', { name: 'Workflow actions' })
    await kebab.click()
    await app.getByRole('menuitem', { name: 'Import workflow' }).click()

    const fileInput = app.locator('input[type="file"][accept=".json"]')
    await fileInput.setInputFiles(importFile)

    const dialog = app.getByRole('dialog', { name: 'Import workflow?' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('radio', { name: /Import as new workflow/ })).toBeVisible()
    await expect(dialog.getByRole('radio', { name: /Import into current workflow/ })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Import' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible()

    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
    unlinkSync(importFile)
  }
})

test('import into current workflow overwrites canvas and saves', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-import-current')
  const importName = buildUniqueName('e2e-imported-current')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Original action')
  const importFile = createImportFile(importName)

  try {
    await openWorkflowInBuilder(app, workflowName, id)
    const originalUrl = app.url()

    const kebab = app.getByRole('button', { name: 'Workflow actions' })
    await kebab.click()
    await app.getByRole('menuitem', { name: 'Import workflow' }).click()

    const fileInput = app.locator('input[type="file"][accept=".json"]')
    await fileInput.setInputFiles(importFile)

    const dialog = app.getByRole('dialog', { name: 'Import workflow?' })
    await expect(dialog).toBeVisible()

    await dialog.getByRole('radio', { name: /Import into current workflow/ }).click()
    await dialog.getByRole('button', { name: 'Import' }).click()
    await expect(dialog).not.toBeVisible()

    expect(app.url()).toBe(originalUrl)
  } finally {
    await deleteWorkflow(app, workflowName)
    unlinkSync(importFile)
  }
})

test.skip('import as new workflow creates a new workflow and navigates', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-import-new')
  const importName = buildUniqueName('e2e-imported-new')
  const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Original action')
  const importFile = createImportFile(importName)

  try {
    await openWorkflowInBuilder(app, workflowName, id)
    const originalUrl = app.url()

    const kebab = app.getByRole('button', { name: 'Workflow actions' })
    await kebab.click()
    await app.getByRole('menuitem', { name: 'Import workflow' }).click()

    const fileInput = app.locator('input[type="file"][accept=".json"]')
    await fileInput.setInputFiles(importFile)

    const dialog = app.getByRole('dialog', { name: 'Import workflow?' })
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: 'Import' }).click()
    await expect(dialog).not.toBeVisible()

    await expect(app).toHaveURL(/workflow-builder\/.+/)
    expect(app.url()).not.toBe(originalUrl)

    await expect(app.getByText('Workflow imported')).toBeVisible()
  } finally {
    await deleteWorkflow(app, workflowName)
    await deleteWorkflow(app, importName)
    unlinkSync(importFile)
  }
})

test('no confirmation modal when importing into a new workflow', async ({ app }) => {
  const importName = buildUniqueName('e2e-import-direct')
  const importFile = createImportFile(importName)

  try {
    await startWorkflowWithTrigger(app)

    const kebab = app.getByRole('button', { name: 'Workflow actions' })
    await kebab.click()
    await app.getByRole('menuitem', { name: 'Import workflow' }).click()

    const fileInput = app.locator('input[type="file"][accept=".json"]')
    await fileInput.setInputFiles(importFile)

    const dialog = app.getByRole('dialog', { name: 'Import workflow?' })
    await expect(dialog).not.toBeVisible({ timeout: 2000 })
  } finally {
    unlinkSync(importFile)
  }
})
