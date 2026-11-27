/** Kafka draft gating across first save/navigation and reload, using advisory-save API responses. */
import { expect, test, toAppUrl, type Page } from './fixtures'
import { mockKafkaAdvisorySaves } from './helpers/kafka-publish-validation'
import {
  buildUniqueName,
  clickAddConnectedStep,
  clickNode,
  clickSaveAndWait,
  fillCodeEditor,
  selectProjectIfRequired,
} from './helpers/workflows'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { createProjectViaApi, deleteProjectViaApi, deleteWorkflowViaApi } from './utils/api'

async function expectDraftGate(app: Page) {
  await expect(app.getByRole('button', { name: 'Run', exact: true })).toHaveAttribute('aria-disabled', 'true')
  await expect(app.getByRole('button', { name: 'Publish workflow', exact: true })).toHaveAttribute(
    'aria-disabled',
    'true'
  )
}

test('unfinished Kafka draft stays gated with findings after first save and reload', async ({ app }) => {
  test.setTimeout(120_000)
  const name = buildUniqueName('kafka-draft-gate')
  const project = await createProjectViaApi(app, name)
  let workflowId: string | undefined
  try {
    if (!isSkipWebServerForPlaywrightTests()) await mockKafkaAdvisorySaves(app, { omitCreatedVersion: true })
    await app.goto(toAppUrl('/workflow-builder/new'))
    await app.getByRole('button', { name: 'Manual trigger', exact: true }).click()
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await app.getByPlaceholder('Workflow name').fill(name)
    await selectProjectIfRequired(app, name)
    const panel = await clickAddConnectedStep(app)
    await panel.getByRole('button', { name: 'Action', exact: true }).click()
    await panel.getByRole('button', { name: 'Kafka Publish', exact: true }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Unfinished publish')
    await fillCodeEditor(app, { value: '{"result":', label: 'JSON payload', inputMethod: 'insertText' })
    await app.getByRole('button', { name: 'Create', exact: true }).click()
    await clickSaveAndWait(app)
    workflowId = new URL(app.url()).pathname.split('/').at(-1)
    await expectDraftGate(app)
    await expect(app.getByTestId('validation-error-badge')).toBeVisible()

    await app.reload()
    await expectDraftGate(app)
    await expect(app.getByTestId('validation-error-badge')).toBeVisible()
    await clickNode(app, 'Unfinished publish')
    await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('{"result":')
    await expect(app.getByRole('button', { name: 'Integration', exact: true })).toContainText(
      'Select a Kafka integration'
    )
    await expect(app.getByText(/Verification failed — \d+ issues? found/)).toBeVisible()
    await app.getByRole('button', { name: 'Danger alert details', exact: true }).click()
    if (!isSkipWebServerForPlaywrightTests()) {
      for (const message of [
        'integration_id is required',
        'credential_id is required',
        'topic is required',
        'JSON payload is required',
      ]) {
        await expect(app.getByText(message, { exact: true })).toBeVisible()
      }
    }
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    await deleteProjectViaApi(app, project.id)
  }
})
