import { test, expect, toAppUrl } from '../fixtures'
import { openFormPromptNodeForEditing, workflowIdFromUrl } from '../helpers/formFieldBuilder'
import {
  addFormPromptNode,
  addFormPromptNodeWithSubmittedBranch,
  addManualTrigger,
  addScriptOnHandle,
  configureFormPromptFallbackRouting,
} from '../helpers/v2-nodes'
import {
  buildUniqueName,
  saveAndCloseNodeForm,
  saveWorkflow,
  triggerLayout,
  waitForUIReady,
} from '../helpers/workflows'
import { apiRequest } from '../utils/api'

const FORM_PROMPT_NODE_NAME = 'Intake Form'

test.describe('Form prompt workflow creation', () => {
  test('connects submitted branch, saves, and reloads', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-prompt-branches')
    let workflowId: string | undefined

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual Start')
      await addFormPromptNodeWithSubmittedBranch(app, FORM_PROMPT_NODE_NAME)

      await expect(app.getByRole('heading', { name: 'Intake Form submitted path', exact: true })).toBeVisible({
        timeout: 10_000,
      })

      await saveWorkflow(app, workflowName)
      workflowId = workflowIdFromUrl(app)

      await app.reload()
      await waitForUIReady(app)
      await triggerLayout(app)
      await expect(app.getByRole('heading', { name: FORM_PROMPT_NODE_NAME, exact: true })).toBeVisible({
        timeout: 15_000,
      })
      await expect(app.getByRole('heading', { name: 'Intake Form submitted path', exact: true })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })

  test('connects fallback branch when timeout routes to fallback, saves, and reloads', async ({ app }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-prompt-fallback-branch')
    let workflowId: string | undefined

    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual Start')
      await addFormPromptNode(app, FORM_PROMPT_NODE_NAME)
      await openFormPromptNodeForEditing(app, FORM_PROMPT_NODE_NAME)
      await configureFormPromptFallbackRouting(app)
      await saveAndCloseNodeForm(app, true)

      await triggerLayout(app)
      await addScriptOnHandle(app, 'submitted', `${FORM_PROMPT_NODE_NAME} submitted path`, 'print("submitted")')
      await triggerLayout(app)
      await addScriptOnHandle(app, 'fallback', `${FORM_PROMPT_NODE_NAME} fallback path`, 'print("fallback")')

      await saveWorkflow(app, workflowName)
      workflowId = workflowIdFromUrl(app)

      await app.reload()
      await waitForUIReady(app)
      await triggerLayout(app)
      await expect(app.getByRole('heading', { name: FORM_PROMPT_NODE_NAME, exact: true })).toBeVisible({
        timeout: 15_000,
      })
      await expect(app.getByRole('heading', { name: 'Intake Form submitted path', exact: true })).toBeVisible({
        timeout: 15_000,
      })
      await expect(app.getByRole('heading', { name: 'Intake Form fallback path', exact: true })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})
