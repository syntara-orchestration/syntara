/**
 * Helper functions for adding each v2 workflow node type via the builder UI.
 *
 * V2 node types:
 *   Trigger:      manual, webhook, eda, scheduled
 *   Executors:    script, http_request, agentic, aap_job_template, approval
 *   Control flow: condition, loop (basic)
 *
 * Converge helpers live in v2-nodes-converge.ts.
 * Advanced loop and wait helpers live in v2-nodes-loop.ts.
 *
 * Each helper opens the add-node panel, selects the correct category/type,
 * fills the minimum required form fields, submits, and closes the editor.
 */

import { expect, type Page } from '../fixtures'

import {
  ensureLlmCredential,
  ensureAapIntegration,
  createLlmIntegration,
  deleteLlmIntegration,
  selectLlmCredential,
} from './llm-helpers'
import { addNodePanel, closeNodeEditorPanel, fillCodeEditor } from './workflows'

export { ensureLlmCredential, createLlmIntegration, deleteLlmIntegration, selectLlmCredential }

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Select a category then a subtype within the add-node panel. */
export async function selectCategoryAndType(page: Page, category: string, subtype: string) {
  const panel = addNodePanel(page)
  await panel.getByRole('button', { name: category, exact: true }).click()
  const subtypeBtn = panel.getByRole('button', { name: subtype, exact: true })
  await expect(subtypeBtn).toBeVisible({ timeout: 5_000 })
  await subtypeBtn.click()
}

/** Select a direct (non-category) button in the add-node panel. */
async function selectDirectNodeType(page: Page, label: string | RegExp) {
  const panel = addNodePanel(page)
  const btn = panel.getByRole('button', { name: label })
  await expect(btn).toBeVisible({ timeout: 5_000 })
  await btn.click()
}

// ---------------------------------------------------------------------------
// Trigger
// ---------------------------------------------------------------------------

/** Click "Add connected step" button on an edge and wait for the add-node panel to appear. */
export async function openAddNodePanel(page: Page) {
  const layoutButton = page.getByRole('button', { name: 'Layout' })
  if ((await layoutButton.count()) > 0) {
    await layoutButton.click()
  }

  // Fit the view so all nodes and edge buttons are visible in the viewport
  const fitViewButton = page.getByRole('button', { name: 'Fit view' })
  if ((await fitViewButton.count()) > 0) {
    await fitViewButton.click()
  }

  const addBtn = page.getByRole('button', { name: 'Add connected step' })
  await expect(addBtn.first()).toBeVisible({ timeout: 20_000 })

  // Retry clicking — React Flow edge buttons can be briefly detached during layout animations
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await addBtn.first().click({ force: true, timeout: 5_000 })
      await expect(addNodePanel(page)).toHaveCount(1, { timeout: 5_000 })
      return
    } catch {
      if (attempt === 2) throw new Error('Failed to open add-node panel after 3 attempts')
      await layoutButton.click()
      await expect(addBtn.first()).toBeVisible({ timeout: 5_000 })
    }
  }
}

/** Add a manual trigger. Must be called on a fresh /workflow-builder/new page. */
export async function addManualTrigger(page: Page, name = 'Manual trigger') {
  // Wait for page to finish loading
  await expect(page.getByRole('progressbar', { name: 'Loading' })).not.toBeVisible({ timeout: 15000 })

  // Wait for trigger selection panel with correct heading text
  await expect(page.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Manual trigger' }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  // Panel auto-closes after adding trigger - no manual close needed
}

/** Add a webhook (API) trigger. Must be called on a fresh /workflow-builder/new page. */
export async function addWebhookTrigger(page: Page, name: string, webhookPath: string) {
  // Wait for page to finish loading
  await expect(page.getByRole('progressbar', { name: 'Loading' })).not.toBeVisible({ timeout: 15000 })

  // Wait for trigger selection panel with correct heading text
  await expect(page.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Webhook trigger', exact: true }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('textbox', { name: 'Webhook path' }).fill(webhookPath)
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  // Panel auto-closes after adding trigger - no manual close needed
}

/** Add an EDA (Event-Driven Ansible) trigger. Must be called on a fresh /workflow-builder/new page. */
export async function addEdaTrigger(page: Page, name: string, webhookPath: string) {
  // Wait for page to finish loading
  await expect(page.getByRole('progressbar', { name: 'Loading' })).not.toBeVisible({ timeout: 15000 })

  // Wait for trigger selection panel with correct heading text
  await expect(page.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Event-Driven Ansible trigger', exact: true }).click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('textbox', { name: 'Webhook path' }).fill(webhookPath)
  await page.getByRole('button', { name: 'Create', exact: true }).click()

  // Panel auto-closes after adding trigger - no manual close needed
}

// ---------------------------------------------------------------------------
// Executor nodes
// ---------------------------------------------------------------------------

/** Add a script node (v2 type: "script"). */
export async function addScriptNode(page: Page, name: string, code = 'print("hello")') {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Action', 'Script')
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await expect(nameInput).toBeEditable({ timeout: 5_000 })
  await nameInput.fill(name)
  await fillCodeEditor(page, { value: code })
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/** Add an HTTP request node (v2 type: "http_request"). */
export async function addHttpRequestNode(page: Page, name: string, url = 'https://api.example.com/data') {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Action', 'REST API')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('textbox', { name: 'URL', exact: true }).fill(url)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add a Task Agent node (v2 type: "agentic").
 * Caller must call `createLlmIntegration()` before using this helper
 * so the model dropdown has selectable options.
 */
export async function addAgenticNode(page: Page, name: string, prompt = 'Analyze the data') {
  const { name: credName } = await ensureLlmCredential(page)
  await openAddNodePanel(page)
  await selectDirectNodeType(page, 'Task Agent')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await selectLlmCredential(page, credName)
  await page.getByRole('textbox', { name: 'Prompt', exact: true }).fill(prompt)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add an AAP job template node (v2 type: "aap_job_template").
 *
 * Creates an AAP integration+credential via the API, then fills the
 * Integration/Organization/Job template dropdowns in the node form.
 */
export async function addAapNode(page: Page, name: string) {
  const { name: integrationName, credName } = await ensureAapIntegration(page)

  // Intercept AAP browse endpoints so the form works without a real AAP server.
  // Against a real backend the proxy would fail because ensureAapIntegration
  // creates an integration with a fake base_url.
  const orgRoute = '**/aap/organizations*'
  const jtRoute = '**/aap/job_templates*'
  await page.route(orgRoute, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ count: 1, results: [{ id: 1, name: 'Default' }] }),
    })
  )
  await page.route(jtRoute, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        count: 1,
        results: [{ id: 10, name: 'Deploy App', description: 'Deploy the application', organization: 'Default' }],
      }),
    })
  )

  await openAddNodePanel(page)
  await selectDirectNodeType(page, /AAP/i)
  const jobTemplateBtn = addNodePanel(page).getByRole('button', { name: 'Launch AAP job template' })
  await expect(jobTemplateBtn).toBeVisible({ timeout: 5_000 })
  await jobTemplateBtn.click()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)

  // Select integration
  const integrationToggle = page.getByRole('button', { name: 'Integration', exact: true })
  await expect(integrationToggle).toBeEnabled({ timeout: 10_000 })
  await integrationToggle.click()
  const integrationOption = page.getByRole('option', { name: new RegExp(integrationName) })
  await expect(integrationOption).toBeVisible({ timeout: 15_000 })
  await integrationOption.click()

  // Set up connection with AAP credential
  const setupBtn = page.getByRole('button', { name: 'Set up connection' })
  await expect(setupBtn).toBeVisible({ timeout: 5_000 })
  await setupBtn.click()
  const credDropdown = page.getByRole('button', { name: 'Select a credential' })
  await expect(credDropdown).toBeEnabled({ timeout: 30_000 })
  await credDropdown.click()
  const credOption = page.getByRole('option', { name: credName })
  await expect(credOption).toBeVisible({ timeout: 10_000 })
  await credOption.click()

  // Select organization
  const orgInput = page.getByPlaceholder('Select an organization')
  await expect(orgInput).toBeVisible({ timeout: 15_000 })
  await orgInput.click()
  await expect(page.getByRole('option', { name: 'Default' })).toBeVisible({ timeout: 10_000 })
  await page.getByRole('option', { name: 'Default' }).click()

  // Select job template
  const templateInput = page.getByPlaceholder('Select a job template')
  await expect(templateInput).toBeVisible({ timeout: 15_000 })
  await templateInput.click()
  const deployOption = page.getByRole('option', { name: /Deploy App/i })
  await expect(deployOption).toBeVisible({ timeout: 10_000 })
  await deployOption.click()

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)

  await page.unroute(orgRoute)
  await page.unroute(jtRoute)
}

/** Add an approval node (v2 type: "approval") without completing branches. */
export async function addApprovalNode(page: Page, name: string) {
  await openAddNodePanel(page)
  await selectDirectNodeType(page, 'Approval')
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(name)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add an approval node with a script node on the "approved" branch.
 * This creates a valid workflow that can be saved.
 * The "rejected" branch is optional per validation rules.
 */
export async function addApprovalNodeWithBranch(page: Page, name: string) {
  await addApprovalNode(page, name)

  // Add a node on the "approved" branch to satisfy validation
  // The "rejected" branch is optional

  // Wait for approval node to be fully rendered before interacting with its edges
  await expect(page.getByText(name)).toBeVisible({ timeout: 5000 })

  // Click layout to position nodes and make button edges visible
  const layoutButton = page.getByRole('button', { name: 'Layout' })
  if ((await layoutButton.count()) > 0) {
    await layoutButton.click()
  }

  // The approval node creates TWO button edges (to placeholders):
  // 1. One with data-testid="add-node-button-approved"
  // 2. One with data-testid="add-node-button-rejected"
  //
  // We need to click the "approved" button to add a node on the approved branch.

  const approvedButton = page.getByTestId('add-node-button-approved')
  await expect(approvedButton).toBeVisible({ timeout: 5000 })
  await approvedButton.click({ force: true })

  await expect(addNodePanel(page)).toHaveCount(1)

  await selectCategoryAndType(page, 'Action', 'Script')

  // Wait for the form to be fully loaded before filling
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10000 })
  await expect(nameInput).toBeEditable({ timeout: 5000 })

  await nameInput.fill(`${name} - approved action`)
  await fillCodeEditor(page, { value: 'print("approved")' })
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

// ---------------------------------------------------------------------------
// Control flow nodes
// ---------------------------------------------------------------------------

/**
 * Add a conditional node (v2 type: "condition") using the visual expression builder.
 * @param page - Playwright page object
 * @param name - Node name
 * @param config - Condition configuration
 * @param config.field - Field name to compare (e.g., "status")
 * @param config.operator - Comparison operator (default: "is equal to")
 * @param config.value - Value to compare against
 */
export async function addConditionalNode(
  page: Page,
  name: string,
  config: {
    field: string
    operator?: string
    value: string
  }
) {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Conditional')

  // Wait for the form to load
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(name)

  // Fill in Visual expression builder fields
  const fieldInput = page.getByRole('textbox', { name: 'Field', exact: true })
  await expect(fieldInput).toBeVisible({ timeout: 10_000 })
  await fieldInput.fill(config.field)

  // Change operator if specified (defaults to "is equal to")
  if (config.operator && config.operator !== 'is equal to') {
    // Click the operator dropdown toggle (PatternFly custom dropdown)
    await page.getByLabel('Comparison operator').click()
    // Click the desired option from the menu (exact match to avoid partial matches)
    await page.getByRole('option', { name: config.operator, exact: true }).click()
  }

  // Fill in Value
  const valueInput = page.getByRole('textbox', { name: 'Value', exact: true })
  await expect(valueInput).toBeVisible({ timeout: 10_000 })
  await valueInput.fill(config.value)

  // Create
  const saveButton = page.getByRole('button', { name: 'Create', exact: true })
  await expect(saveButton).toBeEnabled({ timeout: 10_000 })
  await saveButton.click()

  await closeNodeEditorPanel(page)
}

/** Add a condition node (v2 type: "condition") without completing branches. */
export async function addConditionNode(page: Page, name: string, expression = 'true') {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Conditional')

  // Wait for the form to load
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)

  // Expression builder has two modes: visual builder or raw expression
  // Switch to raw mode to fill the expression directly
  const editorModeToggle = page.getByRole('button', { name: /Expression editor mode/i })
  await expect(editorModeToggle).toBeVisible()
  await editorModeToggle.click()
  await page.getByRole('option', { name: 'Custom expression' }).click()

  // Wait for raw expression input to appear
  const rawExpressionInput = page.getByLabel(/Raw expression/i)
  await expect(rawExpressionInput).toBeVisible()
  await rawExpressionInput.fill(expression)

  // Click minimize button to close and save
  const closeButton = page.getByRole('button', { name: 'Create', exact: true })
  await expect(closeButton).toBeVisible()
  await closeButton.click()

  await closeNodeEditorPanel(page)
}

/**
 * Add a condition node with a script node on the "true" branch.
 * This creates a valid workflow that can be saved.
 * The "false" branch is optional per validation rules.
 */
export async function addConditionNodeWithBranch(page: Page, name: string, expression = 'true') {
  await addConditionNode(page, name, expression)

  // Add a node on the "true" branch to satisfy validation
  // The "false" branch is optional
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Action', 'Script')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(`${name} - true action`)
  await fillCodeEditor(page, { value: 'print("condition is true")' })
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/** Add a loop node (v2 type: "loop") without completing the loop body. Defaults to "For each" loop. */
/** Helper to select a loop type option with fallback handling */
async function selectLoopTypeOption(page: Page) {
  const allOptions = page.getByRole('option')
  const optionCount = await allOptions.count()

  if (optionCount === 0) {
    // No options available, skip
    return
  }

  // Try to select "For each" if it exists and is enabled
  const forEachOption = page.getByRole('option', { name: 'For each', exact: true })
  const forEachExists = await forEachOption.isVisible().catch(() => false)

  if (forEachExists) {
    const isDisabled = await forEachOption.getAttribute('aria-disabled')
    if (isDisabled !== 'true') {
      await forEachOption.click()
      return
    }
  }

  // Try to select first enabled option
  const enabledOptions = page.getByRole('option').filter({ hasNot: page.locator('[aria-disabled="true"]') })
  const enabledCount = await enabledOptions.count()

  if (enabledCount > 0) {
    await enabledOptions.first().click()
  } else {
    // All options disabled, click first option anyway as fallback
    await allOptions.first().click()
  }
}

export async function addLoopNode(page: Page, name: string, items = '${trigger.items}') {
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Loop')

  // Wait for the form to be fully loaded
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await expect(nameInput).toBeEditable({ timeout: 5_000 })
  await nameInput.fill(name)

  // Handle Type dropdown if present
  const typeSelect = page.getByLabel('Type', { exact: true })
  const typeSelectVisible = await typeSelect.isVisible().catch(() => false)

  if (typeSelectVisible) {
    // Wait for form to finish loading
    await page.waitForTimeout(1000)
    await typeSelect.click()
    // Wait for dropdown options to load
    await page.waitForTimeout(1000)

    await selectLoopTypeOption(page)
  }

  // Fill items expression
  const itemsInput = page.getByRole('textbox', { name: 'Items expression', exact: true })
  const itemsInputVisible = await itemsInput.isVisible().catch(() => false)
  if (itemsInputVisible) {
    await itemsInput.fill(items)
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

/**
 * Add a loop node with a script node in the loop body.
 * This creates a valid workflow that can be saved.
 */
export async function addLoopNodeWithBody(page: Page, name: string, items = '${trigger.items}') {
  await addLoopNode(page, name, items)

  // Add a node in the loop body to satisfy validation
  // Use the "Add connected step" button on the edge
  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Action', 'Script')
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(`${name} - loop body`)
  await fillCodeEditor(page, { value: 'print("processing item")' })
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

// ---------------------------------------------------------------------------
// Switch node
// ---------------------------------------------------------------------------

type SwitchCase = {
  condition: string
  label?: string
}

/**
 * Add a switch node with the given cases.
 *
 * The form opens with 2 default cases. This helper:
 * - Fills conditions from index 0 up to cases.length (adding extra paths as needed)
 * - Removes surplus default cases if cases.length < 2
 *
 * Each case switches the ExpressionBuilder to raw mode before filling the condition
 * string, matching the pattern used by addConditionNode.
 */
export async function addSwitchNodeWithCases(page: Page, name: string, cases: SwitchCase[]) {
  if (cases.length === 0) throw new Error('addSwitchNodeWithCases requires at least one case')

  await openAddNodePanel(page)
  await selectCategoryAndType(page, 'Logic', 'Switch')

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(name)

  // The form defaults to 2 cases. Fill the visible ones first.
  const defaultCaseCount = 2

  for (let i = 0; i < Math.min(cases.length, defaultCaseCount); i++) {
    // ExpressionBuilder uses a PatternFly MenuToggle — click to open, then select option
    await page
      .getByLabel(/Expression editor mode/i)
      .nth(i)
      .click()
    await page.getByRole('option', { name: 'Custom expression', exact: true }).click()
    await page
      .getByLabel(/Raw expression/i)
      .nth(i)
      .fill(cases[i].condition)
    const label0 = cases[i].label
    if (label0) {
      await page.getByLabel(`Path ${i + 1} name`).fill(label0)
    }
  }

  // Add extra cases beyond the default 2
  for (let i = defaultCaseCount; i < cases.length; i++) {
    await page.getByRole('button', { name: 'Add path' }).click()
    await page
      .getByLabel(/Expression editor mode/i)
      .nth(i)
      .click()
    await page.getByRole('option', { name: 'Custom expression', exact: true }).click()
    await page
      .getByLabel(/Raw expression/i)
      .nth(i)
      .fill(cases[i].condition)
    const labelN = cases[i].label
    if (labelN) {
      await page.getByLabel(`Path ${i + 1} name`).fill(labelN)
    }
  }

  // Remove surplus default cases (working from the last index downward to avoid re-indexing)
  for (let i = defaultCaseCount; i > cases.length; i--) {
    await page.getByRole('button', { name: `Remove path ${i}` }).click()
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}

// ---------------------------------------------------------------------------
// Schedule trigger
// ---------------------------------------------------------------------------

type ScheduleTriggerConfig = {
  /**
   * Defaults to 'interval' (Visual schedule builder).
   * 'continuous' is treated as 'interval' with no recurrence.
   */
  scheduleType?: 'interval' | 'continuous' | 'cron'
  /**
   * Frequency for interval mode. Maps to the Frequency dropdown.
   * Only used when scheduleType is 'interval'.
   */
  cadence?: 'daily' | 'weekly' | 'monthly' | 'annually'
  /**
   * Start date string (MM/DD/YYYY). Only used when scheduleType is 'interval'.
   * Defaults to '01/15/2030'.
   */
  startDate?: string
}

/**
 * Add a schedule trigger. Must be called on a fresh /workflow-builder/new page.
 *
 * 'continuous' scheduleType maps to interval mode with no recurring cadence.
 */
export async function addScheduleTrigger(page: Page, name: string, config?: ScheduleTriggerConfig) {
  await expect(page.getByRole('progressbar', { name: 'Loading' })).not.toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: /select a trigger node/i })).toBeVisible({ timeout: 10_000 })

  await page.getByRole('button', { name: 'Schedule trigger' }).click()

  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(name)

  // 'continuous' has no equivalent in the UI — map to 'interval' with no cadence
  const uiScheduleType = config?.scheduleType === 'continuous' ? 'interval' : (config?.scheduleType ?? 'interval')
  const scheduleExpressionSelect = page.getByLabel('Schedule expression', { exact: true })
  await expect(scheduleExpressionSelect).toBeVisible()
  // Schedule expression is a PatternFly MenuToggle — click to open, then select by option text
  const scheduleTypeLabels: Record<string, string> = {
    interval: 'Visual schedule builder',
    cron: 'Custom cron expression',
  }
  await scheduleExpressionSelect.click()
  await page.getByRole('option', { name: scheduleTypeLabels[uiScheduleType], exact: true }).click()

  if (uiScheduleType === 'interval') {
    const cadence = config?.cadence
    if (cadence) {
      const frequencyLabels: Record<string, string> = {
        daily: 'Daily',
        weekly: 'Weekly',
        monthly: 'Monthly',
        annually: 'Yearly',
      }
      await page.getByLabel('Frequency', { exact: true }).click()
      await page.getByRole('option', { name: frequencyLabels[cadence], exact: true }).click()
    }

    const startDate = config?.startDate ?? '01/15/2030'
    const startDateInput = page.getByLabel('Start date', { exact: true })
    await expect(startDateInput).toBeVisible()
    await startDateInput.fill(startDate)
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await closeNodeEditorPanel(page)
}
