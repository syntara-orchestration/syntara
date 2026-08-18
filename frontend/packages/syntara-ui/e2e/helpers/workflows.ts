import { randomUUID } from 'node:crypto'

import { type Page } from '@playwright/test'

import { expect, toAppUrl } from '../fixtures'
import {
  createBasicWorkflowViaApi,
  deleteWorkflowViaApi,
  ensureProject,
  findWorkflowIdByName,
  publishWorkflowViaApi,
} from '../utils/api'

export { createBasicWorkflowViaApi, publishWorkflowViaApi }

export const buildUniqueName = (prefix: string) => `${prefix}-${Date.now()}-${randomUUID()}`

export const addNodePanel = (page: Page) =>
  page.getByRole('region', {
    name: /add step|select an action node|select a trigger node|select a logic node|select an aap execution node/i,
  })

/**
 * Wait for UI to be ready by ensuring no toast notifications or loading overlays are blocking interactions
 */
export async function waitForUIReady(page: Page) {
  // Wait for any active toast items to disappear. The AlertGroup container is always
  // mounted even when empty — scope to items *inside* it so an empty group resolves
  // immediately instead of timing out.
  const toastItems = page.locator('.pf-v6-c-alert-group .pf-v6-c-alert')
  await toastItems
    .first()
    .waitFor({ state: 'hidden', timeout: 5000 })
    .catch(() => {})

  // Wait for loading states to clear
  const loadingStates = page.getByLabel('Loading')
  await loadingStates
    .first()
    .waitFor({ state: 'hidden', timeout: 10000 })
    .catch(() => {})
}

/**
 * Click the "Reset layout" button to trigger an auto-layout of the canvas.
 * Uses explicit `toBeVisible()` to ride out any layout animations still settling
 * from a previous call (e.g. after addScriptNode).
 */
export async function triggerLayout(page: Page) {
  const layoutButton = page.getByRole('button', { name: 'Reset layout', exact: true })
  await expect(layoutButton).toBeVisible({ timeout: 10000 })
  await layoutButton.click()
  await waitForUIReady(page)
}

/**
 * Click "Layout" to position nodes and reveal edge buttons,
 * then click "Add connected step" and return the add-node panel.
 */
export async function clickAddConnectedStep(page: Page) {
  // Wait for any toast notifications or loading states to clear
  await waitForUIReady(page)

  const layoutButton = page.getByRole('button', { name: 'Reset layout', exact: true })
  await expect(layoutButton).toBeVisible({ timeout: 10000 })
  await layoutButton.click()

  // Wait again after layout completes
  await waitForUIReady(page)

  // Wait for canvas to finish re-rendering after layout and "Add connected step" buttons to appear
  await expect(async () => {
    const addBtn = page.getByRole('button', { name: 'Add connected step' })
    await expect(addBtn.first()).toBeVisible()
  }).toPass({ timeout: 10000, intervals: [500] })

  const addBtn = page.getByRole('button', { name: 'Add connected step' })
  await addBtn.first().click()

  const panel = addNodePanel(page)
  await expect(panel).toHaveCount(1)

  // Wait for panel to be fully loaded and stable
  await expect(async () => {
    const firstCategoryBtn = panel.getByRole('button', { name: 'Action', exact: true })
    await expect(firstCategoryBtn).toBeVisible()
    await expect(firstCategoryBtn).toBeEnabled()
  }).toPass({ timeout: 15000, intervals: [500, 1000] })

  return panel
}

export async function closeNodeEditorPanel(page: Page) {
  // The node editor cancel button has different aria-labels depending on mode:
  //   edit mode  → "Cancel without saving"
  //   add mode   → "Cancel step creation"
  //   read-only  → "Close node editor"
  // Try each in order.
  const cancelEditButton = page.getByRole('button', { name: 'Cancel without saving' })
  if ((await cancelEditButton.count()) > 0) {
    await expect(cancelEditButton).toBeVisible()
    await cancelEditButton.click()
    await expect(cancelEditButton).toHaveCount(0, { timeout: 10000 })
    return
  }
  const cancelAddButton = page.getByRole('button', { name: 'Cancel step creation' })
  if ((await cancelAddButton.count()) > 0) {
    await expect(cancelAddButton).toBeVisible()
    await cancelAddButton.click()
    await expect(cancelAddButton).toHaveCount(0, { timeout: 10000 })
    return
  }
  // Scope the "Close" button query to the drawer panel to avoid matching alert close buttons
  const drawer = page.locator('.pf-v6-c-drawer__panel')
  const closeButton = drawer.getByRole('button', { name: 'Close node editor' })
  if ((await closeButton.count()) > 0) {
    await expect(closeButton).toBeVisible()
    await closeButton.click()
    await expect(closeButton).toHaveCount(0, { timeout: 10000 })
  }
}

/**
 * Save and close a node form by clicking Create/Update button.
 * Waits for the button to detach (form closed) and optionally verifies the node appears on canvas.
 *
 * @param page - Playwright Page instance
 * @param isUpdate - If true, clicks "Update" button; otherwise clicks "Create" button
 * @param nodeName - Optional node name to verify it appears on canvas after saving
 */
export async function saveAndCloseNodeForm(page: Page, isUpdate = false, nodeName?: string) {
  const buttonName = isUpdate ? 'Update' : 'Create'
  const saveButton = page.getByRole('button', { name: buttonName })
  await expect(saveButton).toBeEnabled()
  await saveButton.click()

  // Wait for negative signal (button detaches - form closed)
  await expect(page.getByRole('button', { name: buttonName })).not.toBeAttached({ timeout: 15_000 })

  await waitForUIReady(page)
  await closeNodeEditorPanel(page)

  // Wait for positive signal (node appears on canvas) if node name provided
  if (nodeName) {
    await verifyNodeVisible(page, nodeName)
  }
}

/**
 * Open a node for editing by double-clicking it on the canvas.
 * Uses toPass retry pattern to handle React Flow rendering delays.
 *
 * @param page - Playwright Page instance
 * @param nodeName - Name of the node to open
 */
export async function openNodeForEditing(page: Page, nodeName: string) {
  const node = page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeName })
  await waitForUIReady(page)

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(async () => {
    await node.dblclick({ force: true })
    await expect(nameInput).toBeVisible()
  }).toPass({ timeout: 15_000, intervals: [1_000, 2_000, 3_000] })
}

export async function fillCodeEditor(
  page: Page,
  { value, label = 'Script code editor' }: { value: string; label?: string }
) {
  const typeInto = async (target: ReturnType<Page['locator']>) => {
    const textbox = target.getByRole('textbox', { name: label }).first()
    const monacoSurface = target.locator('.monaco-editor').first()

    // Wait for Monaco to finish async initialization — either the accessible
    // textbox or the .monaco-editor wrapper must be present before interacting.
    await expect(async () => {
      const hasTextbox = await textbox.isVisible()
      const hasMonaco = await monacoSurface.isVisible()
      if (!hasTextbox && !hasMonaco) throw new Error('Monaco editor not ready')
    }).toPass({ timeout: 15000, intervals: [500, 1000] })

    if (await textbox.isVisible()) {
      await textbox.click({ force: true })
      await page.keyboard.press('ControlOrMeta+A')
      await page.keyboard.type(value, { delay: 10 })
      await expect(textbox).toHaveValue(value)
      return
    }

    await monacoSurface.click({ force: true })
    const usedMonacoApi = await page.evaluate((text) => {
      const w = window as unknown as Record<string, unknown>
      const editor = w.monaco
        ? (
            w.monaco as { editor: { getEditors: () => Array<{ setValue: (v: string) => void }> } }
          ).editor.getEditors()[0]
        : null
      if (editor) {
        editor.setValue(text)
        return true
      }
      const el = document.querySelector('.monaco-editor')
      if (el) {
        const textarea = el.querySelector('textarea')
        if (textarea) {
          textarea.focus()
          document.execCommand('selectAll')
          document.execCommand('insertText', false, text)
        }
      }
      return false
    }, value)
    if (!usedMonacoApi) {
      await expect(monacoSurface.locator('.view-lines')).toContainText(value.slice(0, 20))
    }
  }

  // Wait for at least one editor variant to appear
  await expect(async () => {
    const inlineCount = await page.getByTestId('inline-code-editor').locator(':visible').count()
    const modalCount = await page.getByTestId('modal-code-editor').locator(':visible').count()
    const roleCount = await page.getByRole('textbox', { name: label }).count()

    if (inlineCount === 0 && modalCount === 0 && roleCount === 0) {
      throw new Error('No code editor found')
    }
  }).toPass({ timeout: 15000, intervals: [500, 1000] })

  const visibleInlineEditor = page.getByTestId('inline-code-editor').locator(':visible').first()
  if ((await visibleInlineEditor.count()) > 0) {
    await typeInto(visibleInlineEditor)
    return
  }

  const visibleModalEditor = page.getByTestId('modal-code-editor').locator(':visible').first()
  if ((await visibleModalEditor.count()) > 0) {
    await typeInto(visibleModalEditor)
    return
  }

  const roleEditor = page.getByRole('textbox', { name: label }).first()
  await expect(roleEditor).toBeVisible()
  await roleEditor.click({ force: true })
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.type(value, { delay: 10 })
  await expect(roleEditor).toHaveValue(value)
}

/**
 * Select the first available project from a typeahead project selector dropdown.
 * Works on both mock API (where projects are available immediately) and real backend
 * (where project names vary). Skips "All projects" and "Create project" options.
 */
export async function selectFirstProject(page: Page) {
  const projectInput = page.getByPlaceholder(/All projects|Select a project/)
  const hasInput = await projectInput
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!hasInput) return

  await projectInput.click()
  await page.getByRole('option').first().waitFor({ state: 'visible', timeout: 10_000 })

  // Retry until a real project option appears — API-loaded options arrive after
  // static ones ("All projects", "Create project") on slower CI backends.
  await clickFirstRealProjectOption(page)

  // Wait for the "Select a project" placeholder to disappear before returning.
  // Use not.toBeVisible (not not.toHaveAttribute) because the element may be
  // removed from the DOM entirely after selection, which causes toHaveAttribute
  // to throw "element(s) not found".
  await expect(page.getByPlaceholder('Select a project')).not.toBeVisible()
}

/**
 * Select a project in the builder toolbar.
 * Required for new workflows on the real backend (Save is disabled without a project).
 * Falls back silently when the project selector is absent (e.g. mock API).
 */
export async function selectProjectIfRequired(page: Page, projectName?: string) {
  const projectInput = page.getByPlaceholder(/Select a project/)
  // Use a short timeout — if the project is already selected ("default" shows
  // in the toggle with no "Select a project" placeholder), the element will
  // never appear and a 15s wait burns most of the test budget unnecessarily.
  const needsSelection = await projectInput
    .waitFor({ state: 'visible', timeout: 2_000 })
    .then(() => true)
    .catch(() => false)
  if (!needsSelection) return

  // The placeholder is briefly "Select a project" before the Zustand store
  // restores a previously selected project and re-renders the toggle.
  // Re-check that the locator still matches; if it vanished, a project is
  // already selected and no action is needed.
  if ((await projectInput.count()) === 0) return

  await projectInput.click()
  await page.getByRole('option').first().waitFor({ state: 'visible', timeout: 10_000 })

  if (projectName) {
    const option = page.getByRole('option', { name: projectName })
    await option.waitFor({ state: 'visible', timeout: 15_000 })
    await option.click()
  } else {
    await clickFirstRealProjectOption(page)
  }
}

async function clickFirstRealProjectOption(page: Page) {
  // First try: wait for an API-loaded project to appear
  const found = await trySelectRealProject(page)
  if (found) return

  // No real projects exist — create one via the "Create project" UI option
  await createProjectViaDropdown(page)
}

async function trySelectRealProject(page: Page): Promise<boolean> {
  try {
    await expect(async () => {
      const options = page.getByRole('option')
      if ((await options.count()) === 0) {
        const toggle = page.getByPlaceholder(/All projects|Select a project/)
        if ((await toggle.count()) > 0) await toggle.click()
        await options.first().waitFor({ state: 'visible', timeout: 3_000 })
      }

      const count = await options.count()
      for (let i = 0; i < count; i++) {
        const text = await options.nth(i).textContent()
        if (
          text &&
          !text.includes('All projects') &&
          !text.includes('Create project') &&
          !text.toLowerCase().includes('built-in')
        ) {
          await options.nth(i).click()
          return
        }
      }
      throw new Error('No real project options yet')
    }).toPass({ timeout: 15_000 })
    return true
  } catch {
    return false
  }
}

async function createProjectViaDropdown(page: Page) {
  const options = page.getByRole('option')
  if ((await options.count()) === 0) {
    const toggle = page.getByPlaceholder(/All projects|Select a project/)
    if ((await toggle.count()) > 0) await toggle.click()
    await options.first().waitFor({ state: 'visible', timeout: 5_000 })
  }

  await page.getByRole('option', { name: 'Create project' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('textbox', { name: 'Project name' }).fill('default')
  await dialog.getByRole('button', { name: 'Create project' }).click()

  // Wait for dialog to close (project created)
  await expect(dialog).not.toBeVisible({ timeout: 15_000 })
}

/** Delete a workflow by unique name. Prefers API delete; falls back to UI kebab flow. */
export async function deleteWorkflow(page: Page, workflowName: string) {
  if (page.isClosed()) return
  try {
    const workflowId = await findWorkflowIdByName(page, workflowName)
    if (workflowId) {
      await deleteWorkflowViaApi(page, workflowId)
      return
    }

    await page.goto(toAppUrl('/workflows'))
    await page.getByPlaceholder('Filter by name').fill(workflowName)
    await page.getByRole('button', { name: 'Apply filter' }).click()

    const table = page.getByRole('grid', { name: 'Workflows table' })
    const row = table.getByRole('row', { name: new RegExp(workflowName) })
    const isVisible = await expect(row.first())
      .toBeVisible()
      .then(() => true)
      .catch(() => false)
    if (isVisible) {
      await row
        .getByRole('button', { name: /Actions|Kebab toggle/i })
        .first()
        .click({ force: true })
      await page.getByRole('menuitem', { name: 'Delete workflow' }).click()
      await page.getByRole('checkbox', { name: /I understand this workflow/i }).check()
      await page.getByRole('button', { name: 'Delete' }).click()

      // Wait for deletion to complete - delete dialog should close
      const deleteDialog = page.getByRole('dialog', { name: /Delete workflow/i })
      await expect(deleteDialog).not.toBeVisible({ timeout: 10000 })
    }
  } catch {
    // Best-effort cleanup — don't fail the test
  }
}

/**
 * Delete a project by name via the UI.
 * Best-effort cleanup helper — catches and suppresses errors.
 */
export async function deleteProject(page: Page, projectName: string) {
  if (page.isClosed()) return
  try {
    await page.goto(toAppUrl('/workflows'))

    // Switch to the project in the project selector
    const projectSelector = page.getByPlaceholder(/All projects|Select a project/)
    await projectSelector.click()
    const option = page.getByRole('option', { name: projectName, exact: true })
    const optionExists = await expect(option)
      .toBeVisible()
      .then(() => true)
      .catch(() => false)

    if (!optionExists) return // Project doesn't exist, nothing to delete

    await option.click()

    // Click project kebab menu in page header
    const headerKebab = page.getByRole('button', { name: 'Project actions' })
    const kebabVisible = await expect(headerKebab)
      .toBeVisible()
      .then(() => true)
      .catch(() => false)

    if (!kebabVisible) return // No project actions available

    await headerKebab.click()
    await page.getByRole('menuitem', { name: /Delete project/i }).click()

    // Confirm deletion
    const deleteDialog = page.getByRole('dialog', { name: /Delete project/i })
    await expect(deleteDialog).toBeVisible()
    await deleteDialog.getByRole('checkbox', { name: /I understand/i }).check()
    await deleteDialog.getByRole('button', { name: 'Delete' }).click()

    // Wait for dialog to close
    await expect(deleteDialog)
      .not.toBeVisible({ timeout: 10000 })
      .catch(() => {
        // Best-effort cleanup
      })
  } catch {
    // Best-effort cleanup — don't fail the test
  }
}

/** Navigate directly to the builder for a known workflow ID and wait for the canvas to be ready. */
export async function openBuilderById(page: Page, workflowId: string): Promise<void> {
  await page.goto(toAppUrl(`/workflow-builder/${workflowId}`))
  await selectProjectIfRequired(page)
  await waitForUIReady(page)
  // Confirm the builder actually loaded this workflow (not a 404 or error state)
  await expect(page).toHaveURL(new RegExp(`/workflow-builder/${workflowId}`))
}

/** Open a saved workflow in the builder. Prefer workflowId to skip list filter navigation. */
export async function openWorkflowInBuilder(page: Page, workflowName: string, workflowId?: string) {
  if (workflowId) {
    await openBuilderById(page, workflowId)
    await expect(page.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
    return
  }

  await page.goto(toAppUrl('/workflows'))
  await page.getByPlaceholder('Filter by name').fill(workflowName)
  await page.getByRole('button', { name: 'Apply filter' }).click()

  const table = page.getByRole('grid', { name: 'Workflows table' })
  const row = table.getByRole('row', { name: new RegExp(workflowName) })
  await row.getByRole('link', { name: workflowName, exact: true }).click()
  await expect(page.getByPlaceholder('Workflow name')).toHaveValue(workflowName)
}

export async function createBasicWorkflow(page: Page, workflowName: string, actionName: string) {
  // Ensure a project exists before entering the builder (CI starts with empty DB)
  await ensureProject(page)

  await page.goto(toAppUrl('/workflow-builder/new'))
  await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  // Add manual trigger
  await page.getByRole('button', { name: 'Manual trigger' }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  // Add a connected action node
  const panel = await clickAddConnectedStep(page)
  await panel.getByRole('button', { name: 'Action', exact: true }).click()
  await panel.getByRole('button', { name: 'Script', exact: true }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(actionName)
  await fillCodeEditor(page, { value: 'print("hello")' })
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)

  // Select project (required on real backend), then name and save
  await selectProjectIfRequired(page)

  await page.getByPlaceholder('Workflow name').fill(workflowName)
  await page.getByRole('button', { name: 'Save' }).click()

  // Must navigate away from /new — .+ alone would match "new" and give a false pass
  await expect(page).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })
}

/**
 * Start a new workflow with a manual trigger.
 * Returns after the trigger is added and the editor panel is closed.
 */
export async function startWorkflowWithTrigger(page: Page) {
  await ensureProject(page)
  await page.goto(toAppUrl('/workflow-builder/new'))
  await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  await selectProjectIfRequired(page)

  await page.getByRole('button', { name: 'Manual trigger' }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await page.getByRole('button', { name: 'Create', exact: true }).click()
}

/** Save the workflow with the given name. Waits for URL to confirm persistence. */
export async function saveWorkflow(page: Page, workflowName: string, { timeout = 15_000 } = {}) {
  await selectProjectIfRequired(page)
  await page.getByPlaceholder('Workflow name').fill(workflowName)
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page).toHaveURL(/workflow-builder\/(?!new)/, { timeout })
}

/**
 * Create a basic workflow with only a manual trigger.
 * Saves the workflow and waits for it to be persisted.
 * Canvas is ready after this function returns.
 */
export async function createWorkflowWithTrigger(page: Page, workflowName: string) {
  // Ensure a project exists before entering the builder (CI starts with empty DB)
  await ensureProject(page)

  await page.goto(toAppUrl('/workflow-builder/new'))
  await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  await page.getByRole('button', { name: 'Manual trigger' }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  await selectProjectIfRequired(page)
  const nameInput = page.getByPlaceholder('Workflow name')
  await nameInput.clear()
  await nameInput.fill(workflowName)
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page).toHaveURL(/workflow-builder\/(?!new)/, { timeout: 15_000 })

  await expect(page.getByText('Manual trigger')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset layout', exact: true })).toBeVisible()

  // Wait for canvas to be fully ready
  await waitForUIReady(page)
}

/**
 * Add a Script action node to the workflow canvas.
 */
export async function addScriptNode(page: Page, name: string, code: string) {
  const panel = await clickAddConnectedStep(page)

  const actionBtn = panel.getByRole('button', { name: 'Action', exact: true })
  await expect(actionBtn).toBeVisible({ timeout: 10000 })
  await expect(actionBtn).toBeEnabled({ timeout: 5000 })
  await actionBtn.click()

  // Wait for panel to transition and show action types
  const actionHeading = panel.getByRole('heading', { name: /select an action node/i })
  await expect(actionHeading).toBeVisible({ timeout: 10000 })

  // Wait for panel re-render to complete before clicking Script
  await expect(async () => {
    const scriptBtn = panel.getByRole('button', { name: 'Script', exact: true })
    await expect(scriptBtn).toBeVisible()
    await expect(scriptBtn).toBeEnabled()
  }).toPass({ timeout: 15000, intervals: [500, 1000] })

  const scriptBtn = panel.getByRole('button', { name: 'Script', exact: true })
  await scriptBtn.click()

  await expect(actionHeading).not.toBeVisible({ timeout: 10000 })

  // Wait for form to load and be stable
  await expect(async () => {
    const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
    await expect(nameInput).toBeVisible()
    await expect(nameInput).toBeEditable()
  }).toPass({ timeout: 20000, intervals: [500, 1000] })

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await nameInput.fill(name)

  // Wait for form to be fully loaded before filling code editor
  await waitForUIReady(page)

  await fillCodeEditor(page, { value: code })

  const saveButton = page.getByRole('button', { name: 'Create', exact: true })
  await expect(saveButton).toBeEnabled({ timeout: 20000 })
  await saveButton.click()

  // Wait for the Script form to close — AddNodePanel unmounts immediately when Script
  // is selected so panel.toHaveCount(0) passes instantly and is not a useful gate.
  // Waiting for the Create button to leave the DOM is the real signal that the form unmounted.
  await expect(page.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({ timeout: 15000 })

  // Wait for UI to stabilize
  await waitForUIReady(page)

  // Wait for node to appear on canvas using accessible ARIA attributes
  await expect(page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: name })).toBeVisible({
    timeout: 10000,
  })
}

/**
 * Add a Script action node WITHOUT auto-connecting it (uses "Add step" instead of "Add connected step").
 * Useful for testing manual edge creation.
 */
export async function addScriptNodeUnconnected(page: Page, name: string, code: string) {
  // Wait for any existing panel to close and network to settle
  const panel = addNodePanel(page)
  await expect(panel).toHaveCount(0, { timeout: 10000 })
  await waitForUIReady(page)
  await page.waitForLoadState('networkidle')

  // Retry the entire "Add step" → Action → Script → fill name sequence,
  // because the panel can remount mid-flow when React re-renders the canvas.
  await expect(async () => {
    // Re-click "Add step" each retry in case the panel closed or was never opened
    const addStepBtn = page.getByRole('button', { name: 'Add step' })
    await expect(addStepBtn).toBeVisible()
    await addStepBtn.click()

    await expect(panel).toBeVisible()
    const actionBtn = panel.getByRole('button', { name: 'Action', exact: true })
    await expect(actionBtn).toBeVisible()
    await actionBtn.click()
    const scriptBtn = panel.getByRole('button', { name: 'Script', exact: true })
    await expect(scriptBtn).toBeVisible()
    await scriptBtn.click()
    const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
    await expect(nameInput).toBeVisible()
    await nameInput.fill(name)
  }).toPass({ timeout: 30000, intervals: [2000, 3000] })

  // Wait for form to be fully loaded before filling code editor
  await waitForUIReady(page)

  await fillCodeEditor(page, { value: code })

  const saveButton = page.getByRole('button', { name: 'Create', exact: true })
  await expect(saveButton).toBeEnabled({ timeout: 20000 })
  await saveButton.click()

  // Wait for panel to close
  await expect(panel).toHaveCount(0, { timeout: 15000 })

  // Wait for UI to stabilize
  await waitForUIReady(page)

  // Wait for canvas to render the new node using accessible ARIA attributes
  await expect(page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: name })).toBeVisible({
    timeout: 10000,
  })
}

/**
 * Verify that a node with the given name is visible on the canvas.
 */
export async function verifyNodeVisible(page: Page, nodeName: string) {
  // ReactFlow nodes have role="group" with aria-roledescription="node"
  await expect(page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeName })).toBeVisible({
    timeout: 10000,
  })
}

/**
 * Navigate to the workflow builder and add an API action node form
 * where the credential selector is visible and enabled.
 */
export async function navigateToApiActionForm(page: Page) {
  await ensureProject(page)
  await page.goto(toAppUrl('/workflow-builder/new'))
  await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  await selectProjectIfRequired(page)

  await page.getByRole('button', { name: 'Manual trigger' }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  const panel = await clickAddConnectedStep(page)
  await panel.getByRole('button', { name: 'Action', exact: true }).click()
  await panel.getByRole('button', { name: 'REST API', exact: true }).click()

  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
  const credToggle = page.getByRole('button', { name: 'Authentication credential', exact: true })
  // The CredentialSelector fetches with for_action=use (a separate cache key from
  // HttpCredentialSection's query). It may re-query when projectId populates, so
  // use a longer timeout to cover both the initial and project-scoped fetches.
  await expect(credToggle).toBeEnabled({ timeout: 30_000 })
}

/**
 * Run a single node of workflow via the kebab menu "Run step" action.
 * Pass mockData (JSON string) to use mock data, or omit to run all previous steps.
 * Retries kebab → Run step when React Flow remounts the menu mid-click.
 */
export async function runSingleWorkflowNode(page: Page, nodeName: string, mockData?: string) {
  const node = page.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: nodeName })
  await expect(node).toBeVisible()
  await waitForUIReady(page)
  await node.hover()

  const dialogHeading = page.getByRole('heading', { name: /Run /i })
  await expect(async () => {
    if (
      await page
        .getByRole('menuitem', { name: 'Run step' })
        .isVisible()
        .catch(() => false)
    ) {
      await page.keyboard.press('Escape')
    }
    const kebabButton = node.getByLabel('Step actions menu')
    await expect(kebabButton).toBeVisible()
    await kebabButton.click()
    await page.getByRole('menuitem', { name: 'Run step' }).click({ force: true })
    await expect(dialogHeading).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 30_000, intervals: [500, 1_000, 2_000] })

  if (mockData) {
    await page.getByRole('button', { name: 'Set mock data' }).click()
    await fillCodeEditor(page, { value: mockData })
    await page.getByRole('button', { name: 'Run', exact: true }).click()
  } else {
    await page.getByRole('button', { name: 'Run all previous steps' }).click()
  }

  await expect(page.getByRole('heading', { name: /Most recent run details/i })).toBeVisible()
}
