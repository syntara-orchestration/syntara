/**
 * E2E: Form step RBAC, run validation, stale handling, and accessibility.
 *
 * Coverage map (form step UI plan):
 * - UI-10 allowed_users: submit allowed; non-responder read-only + tooltip (submit hidden)
 * - UI-10 read-only without submit: form-prompt-side-panel.spec.ts (viewer fixture)
 * - UI-11 allowed_groups: member submit; non-member read-only
 * - UI-12 empty allow-lists: any user with form_prompt submit permission
 * - UI-15 invalid dynamic dropdown template at run: run blocked + danger validation (node + bad path)
 * - UI-18 no form_prompt read: execution panel + Tasks tab
 * - UI-19 stale prompt: cancel or workflow delete while panel open (submit blocked + closed after refresh)
 * - Accessibility: keyboard + scoped axe on respond panel (including non-responder read-only)
 */
import AxeBuilder from '@axe-core/playwright'

import { createUnavailableGuard, test, expect, toAppUrl, type Page } from '../fixtures'
import { WCAG_TAGS } from '../fixtures/accessibility'
import { openExecutionFormPromptDeepLink } from '../helpers/formPromptPanel'
import {
  currentUserResponderRef,
  expectDangerToast,
  expectFormStepReadOnlyForNonResponder,
  isRealBackendE2e,
  responderUsernameAllowList,
  submitOpenFormStepAndExpectSuccess,
} from '../helpers/formPromptRbac'
import {
  createPendingFormStepWorkflow,
  disposeFormPromptWorkflow,
  MOCK_FORM_RESPONSE_SEED,
} from '../helpers/formResponses'
import { triggerVerifyWorkflow } from '../helpers/workflow-verify'
import { buildUniqueName, deleteWorkflow, openWorkflowInBuilder } from '../helpers/workflows'
import { apiRequest, cancelExecutionViaApi, createWorkflowViaApi, deleteWorkflowViaApi } from '../utils/api'
async function expectNoA11yViolationsOnResponseForm(page: Page, formPromptId: string): Promise<void> {
  await expect(page.getByRole('heading', { name: 'Respond to prompt' })).toBeVisible()
  const results = await new AxeBuilder({ page })
    .include(`#form-prompt-response-${formPromptId}`)
    .withTags([...WCAG_TAGS])
    .analyze()
  expect(results.violations).toEqual([])
}

// One serial block for the whole file: the in-memory mock API is shared across workers.
test.describe('Form step — RBAC, validation, stale, and a11y', () => {
  test.describe.configure({ mode: 'serial' })

  test.describe('Form step — responder RBAC', { tag: '@pr-check' }, () => {
    test('UI-10: designated responder with submit permission can submit the form step', async ({ app }) => {
      const { username: adminUsername } = await currentUserResponderRef(app)
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-responder-allowed',
        parameters: {
          message: 'Responder allow-list E2E',
          responder_users: responderUsernameAllowList(adminUsername),
          responder_groups: [],
        },
      })

      try {
        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId, {
          expectedMessage: 'Responder allow-list E2E',
        })
        await app.getByRole('textbox', { name: 'Answer' }).fill('allowed responder')
        await submitOpenFormStepAndExpectSuccess(app, created.formPromptId)
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })

    test('UI-10: non-responder sees read-only fields, tooltip, and hidden submit', async ({ app, projectAdminApp }) => {
      test.skip(isRealBackendE2e, 'project-admin persona is mock-only (see service-accounts-integration.spec.ts)')
      const { username: adminUsername } = await currentUserResponderRef(app)
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-responder-deny',
        parameters: {
          message: 'Restricted responders E2E',
          responder_users: responderUsernameAllowList(adminUsername),
          responder_groups: [],
        },
      })

      try {
        await openExecutionFormPromptDeepLink(projectAdminApp, created.executionId, created.formPromptId, {
          expectedMessage: 'Restricted responders E2E',
        })
        await expectFormStepReadOnlyForNonResponder(projectAdminApp)
        await expectNoA11yViolationsOnResponseForm(projectAdminApp, created.formPromptId)
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })

    test('UI-11: group member on allow-list can submit; non-member is read-only with hidden submit', async ({
      app,
      projectAdminApp,
    }) => {
      test.skip(isRealBackendE2e, 'developers group membership and project-admin persona are mock API fixtures')
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-group-responder',
        parameters: {
          message: 'Group responders E2E',
          responder_users: [],
          responder_groups: ['developers'],
        },
      })

      try {
        await openExecutionFormPromptDeepLink(projectAdminApp, created.executionId, created.formPromptId, {
          expectedMessage: 'Group responders E2E',
        })
        await expect(projectAdminApp.getByRole('button', { name: 'Submit response' })).toBeEnabled({ timeout: 20_000 })

        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)
        await expectFormStepReadOnlyForNonResponder(app)
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })

    test('UI-12: empty allow-lists fall back to submit permission only', async ({ app, projectAdminApp }) => {
      test.skip(isRealBackendE2e, 'project-admin persona is mock-only (see service-accounts-integration.spec.ts)')
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-empty-allowlist',
        parameters: {
          message: 'Permission-only responders E2E',
          responder_users: [],
          responder_groups: [],
        },
      })

      try {
        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId, {
          expectedMessage: 'Permission-only responders E2E',
        })
        await expect(app.getByRole('button', { name: 'Submit response' })).toBeEnabled({ timeout: 20_000 })

        await openExecutionFormPromptDeepLink(projectAdminApp, created.executionId, created.formPromptId, {
          expectedMessage: 'Permission-only responders E2E',
        })
        await expect(projectAdminApp.getByRole('button', { name: 'Submit response' })).toBeEnabled({ timeout: 20_000 })
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })
  })

  test.describe('Form step — run validation and access', () => {
    test('UI-15: blocks run when dynamic dropdown template references an invalid node path', async ({ app }) => {
      const workflowName = buildUniqueName('e2e-form-step-invalid-dynamic')
      const nodeName = 'Deploy gate'
      const fieldValueName = 'target_env'
      let workflowId: string | undefined

      try {
        const { id } = await createWorkflowViaApi({
          app,
          name: workflowName,
          triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
          nodes: [
            {
              id: 'form_prompt_1',
              type: 'form_prompt',
              name: nodeName,
              parameters: {
                message: 'Choose deployment target',
                form_definition: {
                  fields: [
                    {
                      value_name: fieldValueName,
                      type: 'dropdown',
                      label: 'Target environment',
                      required: true,
                      options: {
                        source: 'dynamic',
                        expression: '${nonexistent_upstream.output.items}',
                        label_key: 'name',
                        value_key: 'id',
                      },
                    },
                  ],
                },
                responder_users: [],
                responder_groups: [],
              },
            },
            {
              id: 'script_1',
              type: 'script',
              name: 'After submit',
              parameters: { language: 'python', code: 'print("done")' },
            },
          ],
          edges: [
            { from: 'trigger_1', to: 'form_prompt_1' },
            { from: 'form_prompt_1', to: 'script_1', from_port: 'submitted' },
          ],
        })
        workflowId = id
        await openWorkflowInBuilder(app, workflowName, workflowId)
        await triggerVerifyWorkflow(app)

        const runButton = app.getByRole('button', { name: 'Run', exact: true })
        const runBlockedToast = app.getByRole('alert').filter({ hasText: 'Cannot run workflow' })
        const saveIssueHeading = app.getByRole('heading', { name: /Saved with 1 issue/i })
        const verificationFailedHeading = app.getByRole('heading', { name: /Verification failed/i })
        const invalidReferenceLine = app.getByText(/does not exist in this workflow/i)

        await expect(
          verificationFailedHeading.or(saveIssueHeading).or(invalidReferenceLine).or(runBlockedToast)
        ).toBeVisible({ timeout: 20_000 })

        if (await runButton.isEnabled({ timeout: 5_000 }).catch(() => false)) {
          await runButton.click()
          const runConfirm = app.getByRole('button', { name: /Run now|Save and run/ })
          await expect(runConfirm).toBeVisible({ timeout: 10_000 })
          await runConfirm.click()
          await expect(app).not.toHaveURL(/\/executions\//)
          await expect(runBlockedToast.or(saveIssueHeading)).toBeVisible({ timeout: 15_000 })
        } else {
          await expect(runButton).toBeDisabled({ timeout: 15_000 })
        }

        if (await runBlockedToast.isVisible()) {
          await expectDangerToast(app, 'Cannot run workflow', 'nonexistent_upstream')
          await expect(runBlockedToast).toContainText('output.items')
          await expect(runBlockedToast).toContainText(nodeName)
        } else {
          if (!(await invalidReferenceLine.isVisible())) {
            const detailsButton = app.getByRole('button', { name: /alert details/i })
            if (await detailsButton.isVisible().catch(() => false)) {
              await detailsButton.click()
            }
          }
          await expect(invalidReferenceLine).toBeVisible({ timeout: 15_000 })
          await expect(invalidReferenceLine).toContainText('nonexistent_upstream')
          await expect(invalidReferenceLine).toContainText(nodeName)
        }
      } finally {
        if (workflowId) {
          await deleteWorkflowViaApi(app, workflowId).catch(() => undefined)
        } else {
          await deleteWorkflow(app, workflowName).catch(() => undefined)
        }
      }
    })

    test.describe('UI-18: form_prompt read permission', () => {
      const seedGuard = createUnavailableGuard(
        'Form step execution seed required (see syntara-mock-api formPrompts / exec-form-prompt)'
      )

      test.beforeEach(async ({ app }) => {
        const seedResp = await apiRequest(app, 'get', `/form_prompts/${MOCK_FORM_RESPONSE_SEED.pendingId}`)
        const hasSeed = seedResp.ok()
        if (!hasSeed) {
          seedGuard.markUnavailable()
          test.skip(true, 'Form step execution seed required — mock API only (exec-form-prompt)')
        }
      })

      test('user without form_prompt read permission cannot view the form step panel', async ({ userApp }) => {
        await userApp.goto(
          toAppUrl(
            `/executions/${MOCK_FORM_RESPONSE_SEED.executionId}?form_prompt=${MOCK_FORM_RESPONSE_SEED.pendingId}&history=closed`
          )
        )
        await expect(userApp.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
        await expect(userApp.getByText(/do not have permission to view this form prompt/i)).toBeVisible({
          timeout: 20_000,
        })
        await expect(userApp.getByRole('button', { name: 'Submit response' })).not.toBeVisible()
      })

      test('Tasks page hides Form responses tab without form_prompt read', async ({ userApp }) => {
        await userApp.goto(toAppUrl('/tasks/approvals'))
        await expect(userApp.getByRole('heading', { level: 1, name: 'Tasks' })).toBeVisible()
        await expect(userApp.getByRole('tab', { name: 'Form responses' })).not.toBeVisible()
      })
    })
  })

  test.describe('Form step — stale handling and accessibility', () => {
    test('UI-19: cancelled run rejects submit while the form step panel stays open', async ({ app }) => {
      const submitLabel = 'Submit response'
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-stale-cancel',
        parameters: { submit_label: submitLabel },
      })

      try {
        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)
        await app.getByRole('textbox', { name: 'Answer' }).fill('late answer')

        await cancelExecutionViaApi(app, created.executionId)

        await expect(async () => {
          const resp = await apiRequest(app, 'post', `/form_prompts/${created.formPromptId}/submit`, {
            data: { response_data: { answer: 'late answer' } },
          })
          expect(resp.status()).toBe(409)
          const body = (await resp.json()) as { code?: string }
          expect(body.code).toBe('FORM_CANCELLED')
        }).toPass({ timeout: 15_000 })

        const loadTimeout = isRealBackendE2e ? 45_000 : 15_000
        await app.goto(
          toAppUrl(`/executions/${created.executionId}?form_prompt=${created.formPromptId}&history=closed`)
        )
        await expect(app.getByRole('heading', { name: 'Loading execution' })).toHaveCount(0, { timeout: loadTimeout })

        const closedMessage = app.getByText(/no longer accepting responses/i)
        const panelHeading = app.getByRole('heading', { name: 'Respond to prompt' })
        if (await panelHeading.isVisible().catch(() => false)) {
          await expect(closedMessage).toBeVisible({ timeout: 15_000 })
          await expect(app.getByRole('button', { name: submitLabel })).not.toBeVisible()
        } else {
          // Compose dismisses the panel when the form step activity is terminal; stale submit stays blocked.
          await expect(async () => {
            const resp = await apiRequest(app, 'post', `/form_prompts/${created.formPromptId}/submit`, {
              data: { response_data: { answer: 'late answer' } },
            })
            expect(resp.status()).toBe(409)
          }).toPass({ timeout: 15_000 })
        }
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })

    test('UI-19: deleted workflow rejects submit while the form step panel stays open', async ({ app }) => {
      test.skip(isRealBackendE2e, 'Mock API removes executions when a workflow is deleted')
      const created = await createPendingFormStepWorkflow(app, { namePrefix: 'e2e-stale-delete-wf' })

      try {
        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)
        await deleteWorkflowViaApi(app, created.workflowId)

        await expect(async () => {
          const resp = await apiRequest(app, 'post', `/form_prompts/${created.formPromptId}/submit`, {
            data: { response_data: { answer: 'orphaned answer' } },
          })
          expect(resp.status()).toBe(404)
        }).toPass({ timeout: 15_000 })

        await app.reload()
        await app.goto(
          toAppUrl(`/executions/${created.executionId}?form_prompt=${created.formPromptId}&history=closed`)
        )
        await expect(
          app.getByTestId('page-header').getByRole('heading', { name: 'Error loading execution' })
        ).toBeVisible({
          timeout: 30_000,
        })
        await expect(app.getByRole('button', { name: 'Submit response' })).not.toBeVisible()
      } finally {
        // Workflow and execution are removed by deleteWorkflowViaApi in the mock API.
      }
    })

    test('keyboard navigation and axe pass on an open form step respond panel', async ({ app }) => {
      const submitLabel = 'Submit response'
      const created = await createPendingFormStepWorkflow(app, {
        namePrefix: 'e2e-a11y-panel',
        parameters: { submit_label: submitLabel },
      })

      try {
        await openExecutionFormPromptDeepLink(app, created.executionId, created.formPromptId)
        const answerField = app.getByRole('textbox', { name: 'Answer' })
        await answerField.focus()
        await expect(answerField).toBeFocused()
        await app.keyboard.press('Tab')
        await expect(app.getByRole('button', { name: submitLabel })).toBeFocused()

        await expectNoA11yViolationsOnResponseForm(app, created.formPromptId)
      } finally {
        await disposeFormPromptWorkflow(app, created.workflowId, created.executionId)
      }
    })
  })
})
