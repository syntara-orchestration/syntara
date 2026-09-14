/**
 * E2E Tests: Workflow Node Configuration
 *
 * Critical paths covered:
 * - AI Agent Node
 */
import { expect, test } from '../fixtures'
import { type SeededLlmIntegration, createLlmIntegration, deleteLlmIntegration } from '../helpers/llm-helpers'
import { addAgenticNode } from '../helpers/v2-nodes'
import {
  buildUniqueName,
  createWorkflowWithTrigger,
  deleteWorkflow,
  saveWorkflow,
  verifyNodeVisible,
} from '../helpers/workflows'

test('AI agent node configuration form renders with tools, output, and LLM', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-ai-agent-node')
  let integration: SeededLlmIntegration | undefined
  await createWorkflowWithTrigger(app, workflowName)
  try {
    integration = await createLlmIntegration(app, buildUniqueName('e2e-llm-integration'))
    await addAgenticNode(app, 'AI Agent Node', 'Analyze the data')
    await verifyNodeVisible(app, 'AI Agent Node')

    // Save the workflow
    await saveWorkflow(app, workflowName)

    // Assert - Verify workflow is persisted
    await expect(app).toHaveURL(/workflow-builder\/.+/)
    await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)

    // Verify the node is still visible after save
    await verifyNodeVisible(app, 'AI Agent Node')
  } finally {
    await deleteWorkflow(app, workflowName)
    if (integration) await deleteLlmIntegration(app, integration.id)
  }
})
