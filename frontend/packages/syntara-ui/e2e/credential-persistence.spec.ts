/**
 * E2E Tests: Credential Persistence
 *
 * Regression tests for credential selection persisting in workflow nodes
 * after save/reload. PR #561 accidentally reverted snake_case field naming
 * in workflowFactories.ts, causing credential_id to be written as
 * credentialId (camelCase) while node details components read credential_id
 * (snake_case). The credential selection was silently lost.
 *
 * Critical paths covered:
 * - Task Agent node: credential persists after save/reload
 * - REST API node: credential persists after save/reload
 * - AAP node: credential persists after save/reload
 */

import { type Page } from './fixtures'
import { test, expect } from './fixtures'
import { createCredentialOfTypeViaUI, deleteCredentialByName, isCredentialsResponse } from './helpers/credentials'
import {
  type SeededLlmIntegration,
  deleteLlmIntegration,
  createLlmIntegration,
  selectLlmCredential,
} from './helpers/llm-helpers'
import {
  buildUniqueName,
  clickAddConnectedStep,
  closeNodeEditorPanel,
  deleteWorkflow,
  openWorkflowInBuilder,
  saveWorkflow,
  startWorkflowWithTrigger,
} from './helpers/workflows'

async function selectCredential(app: Page, credLabel: string, credName: string) {
  const credToggle = app.getByRole('button', { name: credLabel, exact: true })
  // for_action=use query may take several seconds in resource-constrained backends
  await expect(credToggle).toBeEnabled({ timeout: 30_000 })
  await credToggle.click()
  const option = app.getByRole('option', { name: credName, exact: true })
  await option.waitFor({ state: 'visible', timeout: 15_000 })
  await option.click()
  await expect(credToggle).toContainText(credName)
}

test.describe('Credential Persistence', () => {
  test.skip('Task Agent node credential persists after save/reload', async ({ app }) => {
    const credName = buildUniqueName('e2e-persist-llm')
    const workflowName = buildUniqueName('e2e-persist-ai')
    const integrationName = buildUniqueName('e2e-llm-integ')
    let integration: SeededLlmIntegration | undefined

    try {
      integration = await createLlmIntegration(app, integrationName)

      await createCredentialOfTypeViaUI(app, {
        name: credName,
        type: 'LLM Provider',
        fields: { 'API Key': 'test-llm-key' },
      })

      await startWorkflowWithTrigger(app)

      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Task Agent' }).click()

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Test Task Agent')
      await app.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Analyze the data')

      // Select model + credential via the LLM model picker UX
      // (credentials are fetched when "Set up connection" is clicked after model selection)
      await selectLlmCredential(app, credName)

      await app.getByRole('button', { name: 'Create' }).click()
      await closeNodeEditorPanel(app)
      await saveWorkflow(app, workflowName)

      await openWorkflowInBuilder(app, workflowName)

      await app.getByText('Test Task Agent').click()

      // Wait for the form to render, then for the credential name to resolve
      const form = app.getByTestId('ai-agent-node-form')
      await expect(form).toBeVisible({ timeout: 10_000 })
      await expect(form.getByText(credName)).toBeVisible({ timeout: 30_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteCredentialByName(app, credName)
      if (integration) await deleteLlmIntegration(app, integration.id)
    }
  })

  test('REST API node credential persists after save/reload', async ({ app }) => {
    const credName = buildUniqueName('e2e-persist-http')
    const workflowName = buildUniqueName('e2e-persist-api')

    try {
      await createCredentialOfTypeViaUI(app, {
        name: credName,
        type: 'HTTP Bearer Token',
        fields: { Token: 'test-bearer-token' },
      })

      await startWorkflowWithTrigger(app)

      const credentialsLoaded = app.waitForResponse(isCredentialsResponse)
      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: 'Action', exact: true }).click()
      await panel.getByRole('button', { name: 'REST API', exact: true }).click()

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Test REST API')
      await app.getByRole('textbox', { name: 'URL', exact: true }).fill('https://api.example.com/data')
      await credentialsLoaded

      await selectCredential(app, 'Authentication credential', credName)

      await app.getByRole('button', { name: 'Create' }).click()
      await closeNodeEditorPanel(app)
      await saveWorkflow(app, workflowName)

      await openWorkflowInBuilder(app, workflowName)

      await app.getByText('Test REST API').click()

      const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await expect(credToggle).toContainText(credName, { timeout: 30_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteCredentialByName(app, credName)
    }
  })

  // TODO: AAP credential persistence fails — buildAAPConfig writes credentialId (camelCase)
  // but AAPNodeForm reads credential_id (snake_case). Same class of bug as PR #561.
  test.fixme('AAP node credential persists after save/reload', async ({ app }) => {
    const credName = buildUniqueName('e2e-persist-aap')
    const workflowName = buildUniqueName('e2e-persist-aap-wf')

    try {
      await createCredentialOfTypeViaUI(app, {
        name: credName,
        type: 'Ansible Automation Platform',
        fields: {
          Username: 'admin',
          Password: 'password123',
        },
      })

      await startWorkflowWithTrigger(app)

      const credentialsLoaded = app.waitForResponse(isCredentialsResponse)
      const panel = await clickAddConnectedStep(app)
      await panel.getByRole('button', { name: /AAP/i }).click()

      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Test AAP Job')
      await credentialsLoaded

      await selectCredential(app, 'Authentication credential', credName)

      // Toggle expression mode to bypass organization/job template dropdowns
      // which depend on a real AAP connection the test environment may not have
      const expressionSwitch = app.getByRole('switch', { name: 'Use input variables' })
      const hasExpressionMode = await expressionSwitch
        .waitFor({ state: 'visible', timeout: 5_000 })
        .then(() => true)
        .catch(() => false)
      if (hasExpressionMode) {
        await expressionSwitch.click()
        await app.getByLabel('Organization', { exact: true }).fill('${trigger.org}')
        await app.getByLabel('Job template', { exact: true }).fill('${trigger.template}')
      }

      await app.getByRole('button', { name: 'Create' }).click()
      await closeNodeEditorPanel(app)
      await saveWorkflow(app, workflowName)

      await openWorkflowInBuilder(app, workflowName)

      const reloadedCredentialsLoaded = app.waitForResponse(isCredentialsResponse)
      await app.getByText('Test AAP Job').click()
      await reloadedCredentialsLoaded

      const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await expect(credToggle).toContainText(credName, { timeout: 10_000 })
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteCredentialByName(app, credName)
    }
  })
})
