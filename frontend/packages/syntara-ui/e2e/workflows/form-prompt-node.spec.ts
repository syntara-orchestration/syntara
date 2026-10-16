/**
 * E2E Tests: Form step (form_prompt) node — builder configuration and wiring.
 * Enables runtime/UI cases such as UI-10, UI-13, and UI-16.
 */
import { test, expect, toAppUrl } from '../fixtures'
import {
  openFormPromptNodeForEditing,
  readFormPromptDefinitionFromApi,
  readFormPromptStoredParametersFromApi,
  workflowIdFromUrl,
} from '../helpers/formFieldBuilder'
import {
  configureOpenFormPromptNode,
  createFormPromptNodeFromOpenForm,
  expectFormPromptNodeOnCanvas,
  formPromptNodeFormScope,
  openFormPromptNodeFormFromCatalog,
  wireFormPromptSubmittedBranch,
} from '../helpers/formPromptNodeConfig'
import { stubFormPromptSubmitWhoCanUsers } from '../helpers/stubAuthzWhoCan'
import {
  addFormPromptNode,
  addFormPromptNodeWithSubmittedBranch,
  addManualTrigger,
  addScriptOnHandle,
  configureFormPromptFallbackRouting,
} from '../helpers/v2-nodes'
import { triggerVerifyWorkflow } from '../helpers/workflow-verify'
import {
  buildUniqueName,
  createWorkflowWithTrigger,
  deleteWorkflow,
  saveAndCloseNodeForm,
  saveWorkflow,
  selectProjectIfRequired,
  triggerLayout,
  waitForUIReady,
} from '../helpers/workflows'
import { apiRequest, ensureProject } from '../utils/api'

const FORM_PROMPT_NODE_NAME = 'Intake Form'
const VERIFY_BANNER_TIMEOUT = 20_000

test.describe('Form prompt — node configuration', { tag: '@pr-check' }, () => {
  test('UI-13: registers from catalog with canvas metadata and embedded form design', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await addManualTrigger(app, 'Manual Start')
    await openFormPromptNodeFormFromCatalog(app)

    await expect(app.getByRole('tab', { name: 'Parameters' })).toBeVisible()
    await expect(app.getByRole('tab', { name: 'Settings' })).toBeVisible()
    await expect(app.getByText('Responder users', { exact: true })).toBeVisible()
    await expect(app.getByText('Responder groups', { exact: true })).toBeVisible()
    await expect(app.getByRole('heading', { name: 'Form fields' })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Add field' })).toBeVisible()

    await configureOpenFormPromptNode(app, { name: FORM_PROMPT_NODE_NAME })
    await createFormPromptNodeFromOpenForm(app)
    await expectFormPromptNodeOnCanvas(app, FORM_PROMPT_NODE_NAME)
  })

  test('supports manual responder user entry without project-backed who_can list', async ({ app }) => {
    const nodeName = 'Manual responders form'
    await app.goto(toAppUrl('/workflow-builder/new'))
    await addManualTrigger(app, 'Manual Start')
    await openFormPromptNodeFormFromCatalog(app)

    await configureOpenFormPromptNode(app, {
      name: nodeName,
      responderUserManual: 'custom.operator',
    })
    await createFormPromptNodeFromOpenForm(app)
    await openFormPromptNodeForEditing(app, nodeName)
    await expect(formPromptNodeFormScope(app).getByText('custom.operator', { exact: true })).toBeVisible()
  })

  test('UI-16 setup: message, responders, timeout window, and fallback decision persist after save', async ({
    app,
  }) => {
    test.slow()
    const workflowName = buildUniqueName('e2e-form-prompt-config')
    const promptMessage = 'Please complete the intake form'
    const fieldLabel = 'Operator notes'

    await stubFormPromptSubmitWhoCanUsers(app, [{ id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', username: 'demo' }])

    try {
      await ensureProject(app)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app, 'Manual Start')
      await selectProjectIfRequired(app)
      await openFormPromptNodeFormFromCatalog(app)

      await configureOpenFormPromptNode(app, {
        name: FORM_PROMPT_NODE_NAME,
        message: promptMessage,
        responseWindowSeconds: 45 * 60,
        engineDurationSeconds: 900,
        fallbackDecision: 'submit',
        responderUserPicker: 'demo',
        responderGroup: 'admins',
        formFieldLabel: fieldLabel,
      })
      await createFormPromptNodeFromOpenForm(app)
      await wireFormPromptSubmittedBranch(app, FORM_PROMPT_NODE_NAME)

      await selectProjectIfRequired(app)
      await saveWorkflow(app, workflowName)
      const workflowId = workflowIdFromUrl(app)

      const stored = await readFormPromptStoredParametersFromApi(app, workflowId)
      expect(stored.message).toBe(promptMessage)
      expect(stored.response_window).toBe(45 * 60)
      expect(stored.fallback_decision).toBe('submit')
      expect(stored.responder_users).toEqual(['demo'])
      expect(stored.responder_groups).toEqual(['admins'])
      expect(stored.activity_timeout).toBe(900)

      const definition = await readFormPromptDefinitionFromApi(app, workflowId)
      expect(definition.fields[0]?.label).toBe(fieldLabel)

      await app.reload()
      await waitForUIReady(app)
      await openFormPromptNodeForEditing(app, FORM_PROMPT_NODE_NAME)

      await expect(app.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue(promptMessage)
      await expect(app.getByLabel('Minutes')).toHaveValue('45')
      const form = formPromptNodeFormScope(app)
      await expect(form.getByText('demo', { exact: true })).toBeVisible()
      await expect(form.getByText('admins', { exact: true })).toBeVisible()
      await app.getByRole('tab', { name: 'Settings' }).click()
      await expect(app.getByRole('spinbutton', { name: 'Expected duration (seconds)' })).toHaveValue('900')
      await app.getByRole('tab', { name: 'Parameters' }).click()
      await expect(app.getByRole('textbox', { name: 'Field label' })).toHaveValue(fieldLabel)
      await expect(app.getByText('Default field values')).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('UI-10 setup: verification fails when the Submitted branch is not connected', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-form-prompt-missing-submitted')
    let workflowId: string | undefined

    try {
      await createWorkflowWithTrigger(app, workflowName)
      workflowId = workflowIdFromUrl(app)
      await addFormPromptNode(app, FORM_PROMPT_NODE_NAME)
      await expectFormPromptNodeOnCanvas(app, FORM_PROMPT_NODE_NAME)
      // Verify uses the in-memory builder graph; no extra save is required after adding the form node.

      await triggerVerifyWorkflow(app)
      await expect(app.getByRole('heading', { name: /Verification failed/i })).toBeVisible({
        timeout: VERIFY_BANNER_TIMEOUT,
      })
      await expect(app.getByTestId('validation-error-badge')).toHaveCount(1, { timeout: 10_000 })
      await app.getByRole('button', { name: 'Danger alert details' }).click()
      await expect(
        app.getByText(
          new RegExp(`Form "${FORM_PROMPT_NODE_NAME}" is missing a connection from the 'Submitted' branch`, 'i')
        )
      ).toBeVisible({ timeout: 10_000 })
    } finally {
      if (workflowId) {
        await apiRequest(app, 'delete', `/workflows/${workflowId}`).catch(() => {})
      }
    }
  })
})

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
