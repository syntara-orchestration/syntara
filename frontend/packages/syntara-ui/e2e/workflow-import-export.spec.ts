import fs from 'node:fs/promises'

import type { Locator } from '@playwright/test'
import type { V2WorkflowDefinition } from '@syntara/contracts'

import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { createCredentialOfTypeViaUI, deleteCredentialByName, isCredentialsResponse } from './helpers/credentials'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  deleteWorkflow,
  openWorkflowInBuilder,
  clickAddConnectedStep,
  selectProjectIfRequired,
  selectFirstProject,
  closeNodeEditorPanel,
  startWorkflowWithTrigger,
  saveWorkflow,
  verifyNodeVisible,
  waitForUIReady,
} from './helpers/workflows'
import { ensureProject } from './utils/api'

async function downloadAndParseWorkflow(
  page: Page,
  downloadTrigger: () => Promise<void>
): Promise<V2WorkflowDefinition> {
  const downloadPromise = page.waitForEvent('download')
  await downloadTrigger()
  const download = await downloadPromise
  const filePath = await download.path()
  if (!filePath) throw new Error('Download failed: no path returned')
  const content = await fs.readFile(filePath, 'utf-8')
  return JSON.parse(content) as V2WorkflowDefinition
}

async function uploadWorkflowFile(fileInput: Locator, workflowDef: V2WorkflowDefinition): Promise<void> {
  const buffer = Buffer.from(JSON.stringify(workflowDef, null, 2))
  await fileInput.setInputFiles({
    name: 'workflow.json',
    mimeType: 'application/json',
    buffer,
  })
}

async function exportFromWorkflowsList(app: Page, workflowName: string): Promise<V2WorkflowDefinition> {
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  return downloadAndParseWorkflow(app, async () => {
    const row = app.getByRole('row', { name: new RegExp(workflowName) })
    await row.getByRole('button', { name: /Kebab toggle|Actions/i }).click({ force: true })
    await app.getByRole('menuitem', { name: 'Export workflow' }).click()
  })
}

async function importFromWorkflowsList(
  app: Page,
  workflowDef: V2WorkflowDefinition,
  workflowName: string
): Promise<void> {
  await ensureProject(app)
  await selectFirstProject(app)
  // PF6 alert toasts and loading overlays from the project-selector transition can
  // intercept pointer events, silently swallowing the 'Import workflow' click.
  await waitForUIReady(app)

  await app.getByRole('button', { name: 'Import workflow' }).click()
  const dialog = app.getByRole('dialog')
  await expect(dialog).toBeVisible()

  const fileInput = app.locator('input[type="file"]')
  await uploadWorkflowFile(fileInput, workflowDef)
  await dialog.getByLabel(/Workflow name/i).fill(workflowName)

  // If the dialog still shows "Select a project" (project didn't propagate
  // from the list page via Zustand under parallel load), select one now.
  const dialogProjectInput = dialog.getByPlaceholder('Select a project')
  if ((await dialogProjectInput.count()) > 0 && (await dialogProjectInput.isVisible())) {
    await selectFirstProject(app)
    if ((await dialogProjectInput.count()) > 0 && (await dialogProjectInput.isVisible())) {
      await dialogProjectInput.click()
      const realOptions = app.getByRole('option').filter({ hasNotText: /Create project|View more/ })
      await realOptions.waitFor({ state: 'visible', timeout: 10_000 })
      const [realOption] = await realOptions.all()
      await realOption.click()
    }
  }

  await dialog.getByRole('button', { name: /^Import$/i }).click()

  await expect(dialog).not.toBeVisible({ timeout: 15_000 })
}

test.describe('Workflow Import/Export', () => {
  test('exports and re-imports a workflow with equivalent structure', async ({ app }) => {
    const workflowName = buildUniqueName('roundtrip')
    const reimportedName = `${workflowName}-reimported`

    try {
      await createBasicWorkflowViaApi(app, workflowName, 'Test action')
      const exportedDef = await exportFromWorkflowsList(app, workflowName)

      expect(Array.isArray(exportedDef.triggers)).toBe(true)
      expect(Array.isArray(exportedDef.nodes)).toBe(true)
      expect(Array.isArray(exportedDef.edges)).toBe(true)

      await importFromWorkflowsList(app, exportedDef, reimportedName)

      await app.getByRole('link', { name: reimportedName, exact: true }).click()
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(reimportedName)

      const reexportedDef = await downloadAndParseWorkflow(app, async () => {
        await app.getByLabel('Workflow actions').click()
        await app.getByRole('menuitem', { name: 'Export workflow' }).click()
      })

      // Canvas layout positions are assigned on builder open; ignore them for structure equality.
      const withoutPositions = <T extends Record<string, unknown>>(steps: T[]) =>
        steps.map((step) => {
          const copy = { ...step }
          delete copy.position
          return copy
        })
      expect(withoutPositions(reexportedDef.triggers ?? [])).toEqual(withoutPositions(exportedDef.triggers ?? []))
      expect(withoutPositions(reexportedDef.nodes ?? [])).toEqual(withoutPositions(exportedDef.nodes ?? []))
      expect(reexportedDef.edges).toEqual(exportedDef.edges)
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteWorkflow(app, reimportedName)
    }
  })

  test('imports a workflow from the workflows list page', async ({ app }) => {
    const workflowName = buildUniqueName('import-list')
    const workflowDef = {
      triggers: [{ id: 'trigger_manual', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
      nodes: [{ id: 'n1', type: 'script', name: 'Script', parameters: { language: 'python', code: 'print("test")' } }],
      edges: [{ from: 'trigger_manual', to: 'n1' }],
    } as unknown as V2WorkflowDefinition

    try {
      await app.goto(toAppUrl('/workflows'))
      await importFromWorkflowsList(app, workflowDef, workflowName)
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: workflowName, exact: true })).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('exports a workflow from the workflows list page', async ({ app }) => {
    const workflowName = buildUniqueName('export-list')
    try {
      await createBasicWorkflowViaApi(app, workflowName, 'Action 1')
      const exportedDef = await exportFromWorkflowsList(app, workflowName)
      expect(Array.isArray(exportedDef.triggers)).toBe(true)
      expect(Array.isArray(exportedDef.nodes)).toBe(true)
      expect(Array.isArray(exportedDef.edges)).toBe(true)
      expect(exportedDef.triggers.length).toBeGreaterThan(0)
      expect(exportedDef.nodes.length).toBeGreaterThan(0)
      expect(exportedDef.edges.length).toBeGreaterThan(0)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('imports a workflow from the builder toolbar kebab menu', async ({ app }) => {
    const workflowName = buildUniqueName('import-builder')
    const workflowDef = {
      triggers: [{ type: 'manual_trigger', name: 'Imported Trigger' }],
      nodes: [
        {
          id: 'n1',
          type: 'script',
          name: 'Imported Script',
          parameters: { language: 'python', code: 'print("imported")' },
        },
      ],
      edges: [{ from: 'triggers/0', to: 'n1' }],
    } as unknown as V2WorkflowDefinition

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await selectProjectIfRequired(app)

      const fileInput = app.locator('input[type="file"][accept=".json"]')
      await uploadWorkflowFile(fileInput, workflowDef)
      await app.getByLabel('Workflow actions').click()
      await app.getByRole('menuitem', { name: 'Import workflow' }).click()

      await verifyNodeVisible(app, 'Imported Trigger')
      await verifyNodeVisible(app, 'Imported Script')

      await saveWorkflow(app, workflowName)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('exports a workflow from the builder toolbar kebab menu', async ({ app }) => {
    const workflowName = buildUniqueName('export-builder')
    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Builder Action')
      await openWorkflowInBuilder(app, workflowName, id)
      const exportedDef = await downloadAndParseWorkflow(app, async () => {
        await app.getByLabel('Workflow actions').click()
        await app.getByRole('menuitem', { name: 'Export workflow' }).click()
      })
      expect(exportedDef).toHaveProperty('triggers')
      expect(exportedDef).toHaveProperty('nodes')
      expect(exportedDef).toHaveProperty('edges')
      expect(exportedDef.nodes.some((n) => n.name === 'Builder Action')).toBe(true)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('preserves node positions during export and import', async ({ app }) => {
    const workflowName = buildUniqueName('positions')
    const workflowWithPositions = {
      triggers: [
        { id: 'manual_trigger_0', type: 'manual_trigger', name: 'Manual trigger', position: { x: 100, y: 200 } },
      ],
      nodes: [
        {
          id: 'n1',
          type: 'script',
          name: 'Positioned Script',
          parameters: { language: 'python', code: 'print("positioned")' },
          position: { x: 400, y: 300 },
        },
      ],
      edges: [{ from: 'triggers/0', to: 'n1' }],
    } as unknown as V2WorkflowDefinition

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await selectProjectIfRequired(app)

      const fileInput = app.locator('input[type="file"][accept=".json"]')
      await uploadWorkflowFile(fileInput, workflowWithPositions)
      await app.getByLabel('Workflow actions').click()
      await app.getByRole('menuitem', { name: 'Import workflow' }).click()

      await verifyNodeVisible(app, 'Manual trigger')
      await verifyNodeVisible(app, 'Positioned Script')

      const exportedDef = await downloadAndParseWorkflow(app, async () => {
        await app.getByLabel('Workflow actions').click()
        await app.getByRole('menuitem', { name: 'Export workflow' }).click()
      })

      expect(exportedDef.triggers[0].position).toEqual(workflowWithPositions.triggers[0].position)
      const scriptNode = exportedDef.nodes.find((n) => n.name === 'Positioned Script')
      expect(scriptNode).toBeDefined()
      expect(scriptNode?.position).toEqual(workflowWithPositions.nodes[0].position)

      await saveWorkflow(app, workflowName)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('preserves credential references during export and import', async ({ app }) => {
    const workflowName = buildUniqueName('cred-roundtrip')
    const reimportedName = `${workflowName}-reimported`
    const credName = buildUniqueName('e2e-cred')

    try {
      await createCredentialOfTypeViaUI(app, {
        name: credName,
        type: 'HTTP Bearer Token',
        fields: { Token: 'e2e-test-token' },
      })

      await startWorkflowWithTrigger(app)
      const credentialsLoaded = app.waitForResponse(isCredentialsResponse)
      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Action', exact: true }).click()
      await panel.getByRole('button', { name: 'REST API', exact: true }).click()

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('API Call')
      await app.getByRole('textbox', { name: 'URL', exact: true }).fill('https://api.example.com/test')
      await credentialsLoaded

      const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await expect(credToggle).toBeEnabled({ timeout: 10_000 })
      await credToggle.click()
      const credOption = app.getByRole('option', { name: credName, exact: true })
      await credOption.waitFor({ state: 'visible', timeout: 15_000 })
      await credOption.click()
      await expect(credToggle).toContainText(credName)

      await app.getByRole('button', { name: 'Create' }).click()
      await closeNodeEditorPanel(app)
      await saveWorkflow(app, workflowName)

      const exportedDef = await exportFromWorkflowsList(app, workflowName)
      const apiNode = exportedDef.nodes.find((n) => n.type === 'http_request')
      expect(apiNode).toBeDefined()
      const nodeParams = apiNode?.parameters ?? apiNode?.config
      expect(nodeParams).toHaveProperty('credential_id')

      await importFromWorkflowsList(app, exportedDef, reimportedName)

      await app.getByRole('link', { name: reimportedName, exact: true }).click()
      const reloadedCredentialsLoaded = app.waitForResponse(isCredentialsResponse)
      await app.getByText('API Call').click()
      await reloadedCredentialsLoaded

      const reloadedCredToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await expect(reloadedCredToggle).toContainText(credName, { timeout: 10_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteWorkflow(app, reimportedName)
      await deleteCredentialByName(app, credName)
    }
  })

  test('rejects malformed JSON import with inline error', async ({ app }) => {
    const seedName = buildUniqueName('seed-malformed')
    await createBasicWorkflowViaApi(app, seedName, 'Seed action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await selectFirstProject(app)
      await app.getByPlaceholder('Filter by name').fill(seedName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: seedName, exact: true })).toBeVisible({ timeout: 15_000 })

      await waitForUIReady(app)
      await app.getByRole('button', { name: 'Import workflow' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const fileInput = app.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'invalid.json',
        mimeType: 'application/json',
        buffer: Buffer.from('{not valid json!!!}'),
      })
      await dialog.getByLabel(/Workflow name/i).fill(buildUniqueName('invalid-import'))
      await dialog.getByRole('button', { name: /^Import$/i }).click()

      await expect(dialog.getByText(/Expected property name|Unexpected token/i)).toBeVisible()
      await expect(dialog).toBeVisible()
    } finally {
      await deleteWorkflow(app, seedName)
    }
  })

  test('rejects import with missing required fields', async ({ app }) => {
    const seedName = buildUniqueName('seed-missing')
    await createBasicWorkflowViaApi(app, seedName, 'Seed action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await selectFirstProject(app)
      await app.getByPlaceholder('Filter by name').fill(seedName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: seedName, exact: true })).toBeVisible({ timeout: 15_000 })

      await waitForUIReady(app)
      await app.getByRole('button', { name: 'Import workflow' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const fileInput = app.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'invalid.json',
        mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify({ foo: 'bar' })),
      })
      await dialog.getByLabel(/Workflow name/i).fill(buildUniqueName('invalid-import'))
      await dialog.getByRole('button', { name: /^Import$/i }).click()

      await expect(
        dialog.getByText('File is missing required workflow definition fields (triggers, nodes, edges must be arrays)')
      ).toBeVisible()
      await expect(dialog).toBeVisible()
    } finally {
      await deleteWorkflow(app, seedName)
    }
  })

  test('rejects import with invalid node structure', async ({ app }) => {
    const seedName = buildUniqueName('seed-invalid-node')
    await createBasicWorkflowViaApi(app, seedName, 'Seed action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await selectFirstProject(app)
      await app.getByPlaceholder('Filter by name').fill(seedName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: seedName, exact: true })).toBeVisible({ timeout: 15_000 })

      await waitForUIReady(app)
      await app.getByRole('button', { name: 'Import workflow' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const definition = {
        triggers: [{ type: 'manual_trigger' }],
        nodes: [{ name: 'Missing id and type' }],
        edges: [],
      }
      const fileInput = app.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'invalid.json',
        mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(definition)),
      })
      await dialog.getByLabel(/Workflow name/i).fill(buildUniqueName('invalid-import'))
      await dialog.getByRole('button', { name: /^Import$/i }).click()

      await expect(dialog.getByText(/Each node must have "id" and "type" field/)).toBeVisible()
      await expect(dialog).toBeVisible()
    } finally {
      await deleteWorkflow(app, seedName)
    }
  })

  test('rejects import with unsupported schema version', async ({ app }) => {
    const seedName = buildUniqueName('seed-version')
    await createBasicWorkflowViaApi(app, seedName, 'Seed action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await selectFirstProject(app)
      await app.getByPlaceholder('Filter by name').fill(seedName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: seedName, exact: true })).toBeVisible({ timeout: 15_000 })

      await waitForUIReady(app)
      await app.getByRole('button', { name: 'Import workflow' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const definition = {
        schema_version: '1.0.0',
        triggers: [{ type: 'manual_trigger' }],
        nodes: [{ id: 'n1', type: 'script' }],
        edges: [],
      }
      const fileInput = app.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'invalid.json',
        mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(definition)),
      })
      await dialog.getByLabel(/Workflow name/i).fill(buildUniqueName('invalid-import'))
      await dialog.getByRole('button', { name: /^Import$/i }).click()

      await expect(dialog.getByText(/Unsupported schema version.*Expected 2\.0\.0/)).toBeVisible()
      await expect(dialog).toBeVisible()
    } finally {
      await deleteWorkflow(app, seedName)
    }
  })

  test('clears import error and retries successfully with valid file', async ({ app }) => {
    const seedName = buildUniqueName('seed-retry')
    const workflowName = buildUniqueName('retry-import')
    await createBasicWorkflowViaApi(app, seedName, 'Seed action')

    try {
      await app.goto(toAppUrl('/workflows'))
      await selectFirstProject(app)
      await app.getByPlaceholder('Filter by name').fill(seedName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: seedName, exact: true })).toBeVisible({ timeout: 15_000 })

      await waitForUIReady(app)
      await app.getByRole('button', { name: 'Import workflow' }).click()
      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const fileInput = app.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'invalid.json',
        mimeType: 'application/json',
        buffer: Buffer.from('{bad json}'),
      })
      await dialog.getByLabel(/Workflow name/i).fill(buildUniqueName('invalid-import'))
      await dialog.getByRole('button', { name: /^Import$/i }).click()
      await expect(dialog.getByText(/Expected property name|Unexpected token/i)).toBeVisible()

      await dialog.getByRole('button', { name: 'Clear' }).click()
      await expect(dialog.getByText(/Expected property name|Unexpected token/i)).not.toBeVisible()

      // Export the seed workflow to get a guaranteed-valid definition
      await dialog.getByRole('button', { name: 'Cancel' }).click()
      await expect(dialog).not.toBeVisible()
      const validDef = await exportFromWorkflowsList(app, seedName)

      await app.getByRole('button', { name: 'Import workflow' }).click()
      const retryDialog = app.getByRole('dialog')
      await expect(retryDialog).toBeVisible()

      await uploadWorkflowFile(app.locator('input[type="file"]'), validDef)
      await retryDialog.getByLabel(/Workflow name/i).fill(workflowName)

      const dialogProjectInput = retryDialog.getByPlaceholder('Select a project')
      if ((await dialogProjectInput.count()) > 0 && (await dialogProjectInput.isVisible())) {
        await selectFirstProject(app)
      }

      await retryDialog.getByRole('button', { name: /^Import$/i }).click()
      await expect(retryDialog).not.toBeVisible({ timeout: 15_000 })

      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      await expect(app.getByRole('link', { name: workflowName, exact: true })).toBeVisible()
    } finally {
      await deleteWorkflow(app, seedName)
      await deleteWorkflow(app, workflowName)
    }
  })
})
