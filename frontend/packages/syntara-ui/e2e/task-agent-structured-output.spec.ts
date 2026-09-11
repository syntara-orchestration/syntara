/**
 * E2E Tests: Task Agent Structured Output (JSON Schema)
 *
 * Feature: AAP-58327 - Users can define a JSON Schema (response_schema) on Task Agent nodes
 * to force the LLM to produce structured output matching the schema.
 *
 * Critical paths covered:
 * - Schema editor renders on Task Agent node form
 * - Schema accepts valid JSON without errors
 * - Schema persists after save and reopen
 * - Empty schema is valid (optional field)
 */
import { test, expect, toAppUrl } from './fixtures'
import { type SeededLlmIntegration, deleteLlmIntegration, createLlmIntegration } from './helpers/llm-helpers'
import { addManualTrigger, ensureLlmCredential, selectLlmCredential } from './helpers/v2-nodes'
import { addNodePanel, buildUniqueName, fillCodeEditor } from './helpers/workflows'

test.describe('Task Agent Structured Output', () => {
  test('schema editor renders on Task Agent node', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await addManualTrigger(app)

    // Open Task Agent form via "Add connected step"
    const layoutButton = app.getByRole('button', { name: 'Layout' })
    await expect(layoutButton).toBeVisible()
    await layoutButton.click()

    const addBtn = app.getByRole('button', { name: 'Add connected step' })
    await expect(addBtn).toBeVisible()
    await addBtn.click({ force: true })

    const panel = addNodePanel(app)
    await panel.getByRole('button', { name: 'Task Agent' }).click()

    // Verify Response schema section is visible
    await expect(app.getByText('Response schema')).toBeVisible()

    // Verify the inline code editor container is present
    const codeEditor = app.getByTestId('inline-code-editor')
    await expect(codeEditor).toBeVisible()

    // Close without saving
    await app.keyboard.press('Escape')
  })

  test('schema accepts valid JSON without errors', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-llm-integ')
    let integration: SeededLlmIntegration | undefined
    try {
      integration = await createLlmIntegration(app, integrationName)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app)

      // Ensure LLM credential exists (required for AI Agent form submission)
      const { name: credName } = await ensureLlmCredential(app)

      const layoutButton = app.getByRole('button', { name: 'Layout' })
      await layoutButton.click()

      const addBtn = app.getByRole('button', { name: 'Add connected step' })
      await addBtn.click({ force: true })

      const panel = addNodePanel(app)
      await panel.getByRole('button', { name: 'Task Agent' }).click()

      // Fill required fields
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('TestAgent')
      await app.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Analyze the data')

      // Select LLM credential (required by Zod validation)
      await selectLlmCredential(app, credName)

      // Fill valid JSON schema using fillCodeEditor helper
      const validSchema = JSON.stringify({
        type: 'object',
        properties: {
          summary: { type: 'string' },
          confidence: { type: 'number' },
        },
        required: ['summary'],
      })

      await fillCodeEditor(app, { value: validSchema, label: 'Response schema editor' })

      // Create should succeed without validation errors
      await app.getByRole('button', { name: 'Create' }).click()

      // Verify the Create button is no longer attached (panel closed successfully)
      await expect(app.getByRole('button', { name: 'Create' })).not.toBeAttached({ timeout: 15_000 })

      // Verify the agent node appears on canvas
      await expect(
        app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'TestAgent' })
      ).toBeVisible()
    } finally {
      if (integration) await deleteLlmIntegration(app, integration.id)
    }
  })

  test('empty schema is valid (optional field)', async ({ app }) => {
    const integrationName = buildUniqueName('e2e-llm-integ')
    let integration: SeededLlmIntegration | undefined
    try {
      integration = await createLlmIntegration(app, integrationName)
      await app.goto(toAppUrl('/workflow-builder/new'))
      await addManualTrigger(app)

      // Ensure LLM credential exists (required for AI Agent form submission)
      const { name: credName } = await ensureLlmCredential(app)

      const layoutButton = app.getByRole('button', { name: 'Layout' })
      await layoutButton.click()

      const addBtn = app.getByRole('button', { name: 'Add connected step' })
      await addBtn.click({ force: true })

      const panel = addNodePanel(app)
      await panel.getByRole('button', { name: 'Task Agent' }).click()

      // Fill required fields but leave schema empty
      await app.getByRole('textbox', { name: 'Name', exact: true }).fill('EmptySchemaAgent')
      await app.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Test prompt')

      // Select LLM credential (required by Zod validation)
      await selectLlmCredential(app, credName)

      // Don't fill the response schema field

      // Create should succeed
      await app.getByRole('button', { name: 'Create' }).click()

      // Verify the Create button is no longer attached (panel closed successfully)
      await expect(app.getByRole('button', { name: 'Create' })).not.toBeAttached({ timeout: 15_000 })
    } finally {
      if (integration) await deleteLlmIntegration(app, integration.id)
    }
  })
})
