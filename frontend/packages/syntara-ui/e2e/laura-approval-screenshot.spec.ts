/**
 * One-off: create an approval workflow in the live UI, run it, and screenshot
 * the Review approval Message row for Laura (AAP-87735).
 *
 * Do not commit. Do not delete the workflow — it is left running for the screenshot.
 */
import { expect, test, toAppUrl } from './fixtures'
import { navigateToApprovalAndOpen } from './helpers/approvals'
import { addApprovalNodeWithBranch } from './helpers/v2-nodes'
import { closeNodeEditorPanel, createBasicWorkflowViaApi, openWorkflowInBuilder } from './helpers/workflows'
import { pollApprovalVisible, pollExecutionStatus } from './utils/api'

const WORKFLOW_NAME = 'Laura Approval Screenshot'
const APPROVAL_NAME = 'Production Deployment Approval'
const MESSAGE =
  'Review the staging test results and approve deployment of v${trigger.version} to ${trigger.environment}.'
const SCREENSHOT_PATH = '/Users/rghatage/Rishi/syntara-orchestration/syntara/laura-approval-review-panel.png'

test.use({ channel: 'chrome' })

test('create approval workflow and screenshot Review approval Message', async ({ app }) => {
  test.setTimeout(180_000)

  const { id: workflowId } = await createBasicWorkflowViaApi(app, WORKFLOW_NAME, 'Pre-approval step')
  await openWorkflowInBuilder(app, WORKFLOW_NAME, workflowId)

  await addApprovalNodeWithBranch(app, APPROVAL_NAME)

  const approvalNode = app
    .locator('[role="group"][aria-roledescription="node"]')
    .filter({ hasText: APPROVAL_NAME })
    .filter({ hasNotText: 'approved action' })
  await expect(approvalNode).toBeVisible({ timeout: 10_000 })
  await approvalNode.click()

  const promptField = app.locator('#approval-prompt')
  await expect(promptField).toBeVisible({ timeout: 10_000 })
  await promptField.fill(MESSAGE)
  await promptField.blur()
  await closeNodeEditorPanel(app)

  await app.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(app.getByRole('button', { name: 'Run', exact: true })).toBeEnabled({ timeout: 15_000 })

  await app.getByRole('button', { name: 'Run', exact: true }).click()
  await app.getByRole('button', { name: /Run now|Save and run/ }).click()

  await expect(app).toHaveURL(/\/executions\//, { timeout: 20_000 })
  const executionId = app.url().match(/\/executions\/([a-f0-9-]+)/)?.[1]
  expect(executionId).toBeTruthy()

  await pollExecutionStatus(app, executionId!, ['paused'], { timeout: 90_000 })
  await pollApprovalVisible(app, APPROVAL_NAME)

  await navigateToApprovalAndOpen(app, APPROVAL_NAME)
  await expect(app.getByText('Message', { exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(app.getByText(/Review the staging test results/)).toBeVisible()

  await app.screenshot({ path: SCREENSHOT_PATH, fullPage: true })

  // eslint-disable-next-line no-console -- one-off helper: print URLs for the screenshot
  console.log(`workflow_id=${workflowId}`)
  // eslint-disable-next-line no-console
  console.log(`execution_url=${toAppUrl(`/executions/${executionId}`)}`)
  // eslint-disable-next-line no-console
  console.log(`open=${app.url()}`)
  // eslint-disable-next-line no-console
  console.log(`screenshot=${SCREENSHOT_PATH}`)
})
