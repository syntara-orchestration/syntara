/**
 * E2E: Form Trigger stale popup handling (UI-19 / AAP-100038)
 *
 * Open the Form Trigger run dialog from the Workflows list, mutate the workflow in
 * another session (API), then verify submit fails gracefully and no execution starts.
 */
import { test } from '../fixtures'
import {
  createPublishedFormTriggerWorkflow,
  deleteWorkflowViaApiForStaleTest,
  disposeFormTriggerWorkflow,
  expectStaleFormTriggerSubmitBlocked,
  openFormTriggerRunDialogFromWorkflowList,
  republishWorkflowWithoutFormTrigger,
} from '../helpers/formTriggerRun'

test.describe('Form Trigger — stale popup handling (UI-19)', () => {
  test('UI-19: deleted workflow rejects submit while the form trigger popup stays open', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, 'e2e-form-trigger-stale-delete-wf')

    try {
      await openFormTriggerRunDialogFromWorkflowList(app, created.workflowName)
      await deleteWorkflowViaApiForStaleTest(app, created.workflowId)
      await expectStaleFormTriggerSubmitBlocked(app, created.workflowId, created.triggerNodeId)
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId, created.workflowName)
    }
  })

  test('UI-19: removed form trigger rejects submit while the form trigger popup stays open', async ({ app }) => {
    const created = await createPublishedFormTriggerWorkflow(app, 'e2e-form-trigger-stale-remove-node')

    try {
      await openFormTriggerRunDialogFromWorkflowList(app, created.workflowName)
      await republishWorkflowWithoutFormTrigger(app, created.workflowId, created.workflowName)
      await expectStaleFormTriggerSubmitBlocked(app, created.workflowId, created.triggerNodeId)
    } finally {
      await disposeFormTriggerWorkflow(app, created.workflowId, created.workflowName)
    }
  })
})
