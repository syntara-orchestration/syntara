/**
 * E2E Tests: Workflow Verification — Missing Required Configuration (UI-32)
 *
 * Objective: Verify that validation catches nodes with missing required configuration.
 *
 * Test Procedure:
 * 1. Add an AAP Job Template node with no job template selected
 * 2. Trigger verification and check for validation errors
 *
 * Expected Results:
 * - Validation identifies the unconfigured node
 * - The error message specifies which node and which field is missing
 */

import { test, expect, toAppUrl, type Page } from '../fixtures'
import { addManualTrigger, openAddNodePanel } from '../helpers/v2-nodes'
import { triggerVerifyWorkflow } from '../helpers/workflow-verify'
import { buildUniqueName, selectProjectIfRequired, closeNodeEditorPanel, addNodePanel } from '../helpers/workflows'
import { ensureProject, apiRequest } from '../utils/api'

const VERIFY_BANNER_TIMEOUT = 20_000
const ERROR_BADGE_TIMEOUT = 10_000

/**
 * Add an AAP job template node WITHOUT providing the required job template ID.
 * AAP is a category button that leads to a subcategory panel; "Launch AAP job template"
 * must be selected before the node form appears.
 */
async function addIncompleteAapNode(page: Page, name: string) {
  await openAddNodePanel(page)
  // AAP is a category — click it to reveal the subcategory panel, then pick the subtype
  const panel = addNodePanel(page)
  const aapBtn = panel.getByRole('button', { name: /AAP/i })
  await expect(aapBtn).toBeVisible({ timeout: 5_000 })
  await aapBtn.click()

  const subPanel = addNodePanel(page)
  const jobTemplateBtn = subPanel.getByRole('button', { name: 'Launch AAP job template', exact: true })
  await expect(jobTemplateBtn).toBeVisible({ timeout: 10_000 })
  await jobTemplateBtn.click()

  // Fill only the name — intentionally leave job template empty to simulate misconfiguration
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await expect(nameInput).toBeVisible({ timeout: 10_000 })
  await nameInput.fill(name)

  // Create without filling required job template field
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({ timeout: 15_000 })

  await closeNodeEditorPanel(page)
}

test.describe('UI-32: Workflow Verification — Missing Required Configuration', { tag: '@pr-check' }, () => {
  test('unconfigured AAP node triggers verification error', async ({ app }) => {
    // Builds the workflow through the UI before verifying — the default budget is
    // too tight for that plus a verify retry on a loaded cluster.
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-ui32-validation')
    let workflowId: string | undefined

    // ensureProject guarantees a project exists via API; selectProjectIfRequired handles the UI modal on first save
    await ensureProject(app)
    await app.goto(toAppUrl('/workflow-builder/new'))

    try {
      await addManualTrigger(app, 'Start workflow')
      await addIncompleteAapNode(app, 'Incomplete AAP Node')

      // Save and capture the workflow ID for reliable API-based cleanup
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save', exact: true }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: 15_000 })
      workflowId = app.url().match(/workflow-builder\/([a-f0-9-]{36})/)?.[1]

      // Verification is a separate action from save — trigger it via the kebab menu.
      // The helper retries the open+click until the validate request actually responds,
      // so neither a swallowed click nor a slow backend leaves us waiting on a banner
      // that was never going to render.
      await triggerVerifyWorkflow(app)

      // getByRole('heading') is more specific than getByText (avoids matching hidden text)
      await expect(app.getByRole('heading', { name: /Verification failed/i })).toBeVisible({
        timeout: VERIFY_BANNER_TIMEOUT,
      })

      const warningBadge = app.getByTestId('validation-error-badge')
      await expect(warningBadge).toHaveCount(1, { timeout: ERROR_BADGE_TIMEOUT })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})
