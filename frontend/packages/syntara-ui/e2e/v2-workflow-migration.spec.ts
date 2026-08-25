/**
 * V2 Workflow Schema Migration – E2E Tests
 *
 * These tests validate that the UI correctly creates, saves, and renders
 * workflows using the v2 schema format.
 *
 * V2 schema key differences from v1:
 *   - schema_version: "2.0.0" (was schemaVersion: "1.0.0")
 *   - Top-level arrays: triggers[], nodes[], edges[]
 *   - No nested workflow.activities wrapper
 *   - Each executor is its own node type ("script", "http_request", …)
 *     instead of type "task" + task.executor
 *   - Control flow uses port-based edges (from_port: "true"/"false",
 *     "iterate"/"complete") instead of nested then/else/do arrays
 *
 * Run against mock API (default):
 *   npm run e2e -- v2-workflow-migration.spec.ts
 *
 * Run against real backend:
 *   SYNTARA_E2E_BASE_URL=http://localhost:5173 \
 *   SYNTARA_E2E_SKIP_WEB_SERVER=true \
 *   npm run e2e -- v2-workflow-migration.spec.ts
 */
import { test, expect, toAppUrl } from './fixtures'
import {
  addManualTrigger,
  addScriptNode,
  addHttpRequestNode,
  addAgenticNode,
  addAapNode,
  addApprovalNodeWithBranch,
  addConditionNodeWithBranch,
  addLoopNodeWithBody,
  createLlmIntegration,
  deleteLlmIntegration,
} from './helpers/v2-nodes'
import { addConvergeNode } from './helpers/v2-nodes-converge'
import { buildUniqueName, selectProjectIfRequired, deleteWorkflow, triggerLayout } from './helpers/workflows'

/** Inline v2 schema type (formerly in toV2Definition.ts stub, now replaced by generated contracts). */
type V2WorkflowDefinition = {
  schema_version: '2.0.0'
  name: string
  description?: string
  triggers: { id: string; type: string; name?: string; parameters: Record<string, unknown> }[]
  nodes: { id: string; type: string; name?: string; parameters: Record<string, unknown> }[]
  edges: { from: string; to: string; from_port?: string; to_port?: string }[]
}

// ---------------------------------------------------------------------------
// Shared assertion helpers
// ---------------------------------------------------------------------------

/** Assert a workflow_definition payload follows the v2 schema structure. */
function expectV2SchemaStructure(def: V2WorkflowDefinition) {
  // Must use v2 schema version
  expect(def.schema_version).toBe('2.0.0')

  // Must have v2 top-level arrays
  expect(Array.isArray(def.triggers)).toBe(true)
  expect(Array.isArray(def.nodes)).toBe(true)
  expect(Array.isArray(def.edges)).toBe(true)

  // Must NOT contain v1 structures
  expect(def).not.toHaveProperty('workflow') // v1 nesting wrapper
  expect(def).not.toHaveProperty('activities') // v1 flat activities
  expect(def).not.toHaveProperty('schemaVersion') // v1 used camelCase
}

/** Collect all node types (triggers + nodes) from a v2 definition. */
function collectAllTypes(def: V2WorkflowDefinition): string[] {
  return [...def.triggers.map((t) => t.type), ...def.nodes.map((n) => n.type)]
}

/** Extract v2 workflow definition from a save request payload. */
function getV2DefFromRequest(request: { postDataJSON: () => unknown }): V2WorkflowDefinition {
  const payload = request.postDataJSON() as { workflow_definition: V2WorkflowDefinition }
  return payload.workflow_definition
}

/** Extract v2 workflow definition from an API response body. */
function getV2DefFromResponse(body: unknown): V2WorkflowDefinition {
  const data = body as {
    version?: { workflow_definition?: V2WorkflowDefinition }
    workflow_definition?: V2WorkflowDefinition
  }
  return (data.version?.workflow_definition ?? data.workflow_definition) as V2WorkflowDefinition
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('V2 Workflow Schema Migration', () => {
  // -------------------------------------------------------------------------
  // 1. Schema format verification
  // -------------------------------------------------------------------------

  test('workflow save payload uses v2 schema format', async ({ app }) => {
    const workflowName = buildUniqueName('v2-schema-format')
    await app.goto(toAppUrl('/workflow-builder/new'))

    // Build a minimal workflow: manual trigger → script
    await addManualTrigger(app)
    await addScriptNode(app, 'Validate input', 'print("validating")')

    // Intercept the POST /workflows request (select project first to avoid name reset)
    const saveRequestPromise = app.waitForRequest((req) => req.url().includes('/workflows') && req.method() === 'POST')
    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    const saveRequest = await saveRequestPromise
    const def = getV2DefFromRequest(saveRequest)

    // --- V2 structure assertions ---
    expectV2SchemaStructure(def)

    // v2 requires workflow-level name
    expect(def.name).toBe(workflowName)

    // Trigger: v2 format with id, type, parameters
    expect(def.triggers).toHaveLength(1)
    expect(def.triggers[0].type).toBe('manual_trigger')
    expect(def.triggers[0]).toHaveProperty('id')
    expect(def.triggers[0]).toHaveProperty('parameters')

    // Script node: v2 uses type "script" directly (not v1 task wrapper)
    expect(def.nodes).toHaveLength(1)
    expect(def.nodes[0].type).toBe('script')
    expect(def.nodes[0]).toHaveProperty('id')
    expect(def.nodes[0]).toHaveProperty('parameters')
    expect(def.nodes[0]).not.toHaveProperty('task') // no v1 task wrapper

    // Edges connect trigger → script
    expect(def.edges.length).toBeGreaterThanOrEqual(1)
    expect(def.edges[0]).toHaveProperty('from')
    expect(def.edges[0]).toHaveProperty('to')
  })

  // -------------------------------------------------------------------------
  // 2. All executor node types
  // -------------------------------------------------------------------------

  test('creates and saves all v2 executor node types', async ({ app }) => {
    test.setTimeout(120_000)
    const workflowName = buildUniqueName('v2-all-executors')
    await app.goto(toAppUrl('/workflow-builder/new'))

    // Create LLM integration for agentic node
    const llmIntegrationName = buildUniqueName('test-llm-integration')
    const llmIntegration = await createLlmIntegration(app, llmIntegrationName)

    try {
      // Manual trigger + all 5 executor types
      // Note: Approval node must have a branch completed to be valid
      await addManualTrigger(app, 'Start workflow')
      await addScriptNode(app, 'Run script', 'echo "hello"')
      await addHttpRequestNode(app, 'Fetch data', 'https://api.example.com/data')
      await addAgenticNode(app, 'AI analysis', 'Analyze the fetched data')
      await addAapNode(app, 'Deploy with Ansible')
      await addApprovalNodeWithBranch(app, 'Approve deployment')
      // After approval, the workflow ends (the WithBranch helper adds a script on approved branch)
      await triggerLayout(app)

      // Intercept save
      const saveRequestPromise = app.waitForRequest(
        (req) => req.url().includes('/workflows') && req.method() === 'POST'
      )
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      const saveRequest = await saveRequestPromise
      const def = getV2DefFromRequest(saveRequest)

      // Verify v2 schema
      expectV2SchemaStructure(def)

      // All 5 executor node types must be present
      const nodeTypes = def.nodes.map((n) => n.type)
      expect(nodeTypes).toContain('script')
      expect(nodeTypes).toContain('http_request')
      expect(nodeTypes).toContain('agentic')
      expect(nodeTypes).toContain('aap_job_template')
      expect(nodeTypes).toContain('approval')

      // Each node must use v2 direct type (not v1 "task" with executor)
      for (const node of def.nodes) {
        expect(node).not.toHaveProperty('task')
        expect(node).toHaveProperty('parameters')
      }

      // Trigger
      expect(def.triggers[0].type).toBe('manual_trigger')

      // Edges form a chain: trigger → script → http → ai → aap → approval
      expect(def.edges.length).toBeGreaterThanOrEqual(5)

      // Verify workflow appears in workflows list
      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const targetRow = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(targetRow).toBeVisible()
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteLlmIntegration(app, llmIntegration.id)
    }
  })

  // -------------------------------------------------------------------------
  // 3. All control flow node types
  // -------------------------------------------------------------------------

  test('creates and saves all v2 control flow node types', async ({ app }) => {
    const workflowName = buildUniqueName('v2-control-flow')
    await app.goto(toAppUrl('/workflow-builder/new'))

    try {
      // Manual trigger + all 3 control flow types
      await addManualTrigger(app, 'Start')
      await addConditionNodeWithBranch(app, 'Check condition')
      await addLoopNodeWithBody(app, 'Iterate items')
      await addConvergeNode(app, 'Merge branches')

      // Intercept save
      const saveRequestPromise = app.waitForRequest(
        (req) => req.url().includes('/workflows') && req.method() === 'POST'
      )
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      const saveRequest = await saveRequestPromise
      const def = getV2DefFromRequest(saveRequest)

      // Verify v2 schema
      expectV2SchemaStructure(def)

      // All 3 control flow node types present
      const nodeTypes = def.nodes.map((n) => n.type)
      expect(nodeTypes).toContain('condition')
      expect(nodeTypes).toContain('loop')
      expect(nodeTypes).toContain('converge')

      // Condition node: v2 flat parameters (not v1 nested then/else arrays)
      const conditionNode = def.nodes.find((n) => n.type === 'condition')!
      expect(conditionNode).toHaveProperty('parameters')
      expect(conditionNode).not.toHaveProperty('then')
      expect(conditionNode).not.toHaveProperty('else')

      // Loop node: v2 flat parameters (not v1 nested do array)
      const loopNode = def.nodes.find((n) => n.type === 'loop')!
      expect(loopNode).toHaveProperty('parameters')
      expect(loopNode).not.toHaveProperty('do')

      // Converge node: v2 uses parameters.strategy (not v1 nested branches array)
      const convergeNode = def.nodes.find((n) => n.type === 'converge')!
      expect(convergeNode).toHaveProperty('parameters')

      // Edges: condition should produce port-based edges in v2
      const conditionEdges = def.edges.filter((e) => e.from === conditionNode.id)
      const hasTruePort = conditionEdges.some((e) => e.from_port === 'true')
      const hasFalsePort = conditionEdges.some((e) => e.from_port === 'false')
      expect(hasTruePort).toBe(true)
      expect(hasFalsePort).toBe(true)

      // Loop edges should use iterate/complete ports
      const loopEdges = def.edges.filter((e) => e.from === loopNode.id)
      const hasIteratePort = loopEdges.some((e) => e.from_port === 'iterate')
      const hasCompletePort = loopEdges.some((e) => e.from_port === 'complete')
      expect(hasIteratePort).toBe(true)
      expect(hasCompletePort).toBe(true)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  // -------------------------------------------------------------------------
  // 4. Comprehensive round-trip (all 9 node types)
  // -------------------------------------------------------------------------

  test('comprehensive v2 workflow: all node types persist and reload', async ({ app }) => {
    test.setTimeout(120_000)
    const workflowName = buildUniqueName('v2-comprehensive')
    await app.goto(toAppUrl('/workflow-builder/new'))

    // Create LLM integration for agentic node
    const llmIntegrationName = buildUniqueName('test-llm-integration-comprehensive')
    const llmIntegration = await createLlmIntegration(app, llmIntegrationName)

    try {
      // --- Build a workflow with ALL 9 v2 node types ---

      // Trigger
      await addManualTrigger(app, 'Start workflow')

      // Executors (sequential chain)
      await addScriptNode(app, 'Validate input', 'print("validating")')
      await addHttpRequestNode(app, 'Fetch API data', 'https://api.example.com')
      await addAgenticNode(app, 'AI processing', 'Process the data')
      await addAapNode(app, 'Ansible deployment')
      await addApprovalNodeWithBranch(app, 'Manual approval')

      // Control flow
      await addConditionNodeWithBranch(app, 'Branch decision')
      await addLoopNodeWithBody(app, 'Process items')
      await addConvergeNode(app, 'Merge results')

      // --- Save ---
      const saveRequestPromise = app.waitForRequest(
        (req) => req.url().includes('/workflows') && req.method() === 'POST'
      )
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      const saveRequest = await saveRequestPromise
      const def = getV2DefFromRequest(saveRequest)

      // --- Verify v2 payload contains all 9 types ---
      expectV2SchemaStructure(def)

      const allTypes = collectAllTypes(def)
      const expectedTypes = [
        'manual_trigger',
        'script',
        'http_request',
        'agentic',
        'aap_job_template',
        'approval',
        'condition',
        'loop',
        'converge',
      ]
      for (const t of expectedTypes) {
        expect(allTypes, `missing v2 node type: ${t}`).toContain(t)
      }

      // --- Round-trip: navigate away, come back, verify all nodes visible ---
      await expect(app).toHaveURL(/workflow-builder\/.+/)
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()
      const targetRow = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(targetRow).toBeVisible()

      // Reopen the saved workflow
      await targetRow.getByRole('link', { name: workflowName, exact: true }).click()

      // Every node should be present on the canvas after reload.
      // Use accessible group names (not getByText) since React Flow may
      // not render text labels at small zoom levels with many nodes.
      const nodeNames = [
        'Start workflow',
        'Validate input',
        'Fetch API data',
        'AI processing',
        'Ansible deployment',
        'Manual approval',
        'Branch decision',
        'Process items',
        'Merge results',
      ]
      for (const nodeName of nodeNames) {
        await expect(
          app.locator('.react-flow').getByRole('group', { name: new RegExp(`^${nodeName}(,|$)`) }),
          `node "${nodeName}" should be present after reload`
        ).toBeAttached({ timeout: 15_000 })
      }
    } finally {
      await deleteWorkflow(app, workflowName)
      await deleteLlmIntegration(app, llmIntegration.id)
    }
  })

  // -------------------------------------------------------------------------
  // 5. API response format verification
  // -------------------------------------------------------------------------

  test('API response preserves v2 schema format on reload', { tag: ['@konflux-skip'] }, async ({ app }) => {
    const workflowName = buildUniqueName('v2-response-format')
    await app.goto(toAppUrl('/workflow-builder/new'))

    // Create and save a simple workflow (select project first to avoid name reset)
    await addManualTrigger(app)
    await addScriptNode(app, 'Test script', 'print("test")')
    await selectProjectIfRequired(app)
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app).toHaveURL(/workflow-builder\/.+/)

    // Navigate to workflows list, find the saved workflow, and reopen it.
    // This is more reliable than page.reload() which can lose session context.
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()

    // Use route interception to capture the GET response when opening the workflow
    let capturedBody: unknown = null
    await app.route('**/workflows/*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      const response = await route.fetch()
      capturedBody = await response.json()
      await route.fulfill({ response })
    })

    // Click the workflow name to open it in the builder
    await app.getByRole('link', { name: workflowName, exact: true }).click()

    // Wait for the workflow to fully load in the builder
    await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 30000 })

    // Clean up route handler
    await app.unroute('**/workflows/*')

    // The API may nest definition under "version" or return it at top level
    expect(capturedBody).not.toBeNull()
    const def = getV2DefFromResponse(capturedBody)
    expect(def).toBeDefined()

    // Verify the API returned v2 format (not silently down-converted to v1)
    expectV2SchemaStructure(def)

    // Verify specific v2 node types are preserved
    expect(def.triggers[0].type).toBe('manual_trigger')
    expect(def.nodes[0].type).toBe('script')
    expect(def.nodes[0]).not.toHaveProperty('task')
  })

  // -------------------------------------------------------------------------
  // 6. Edit and re-save persists changes
  // -------------------------------------------------------------------------

  test('edit and save workflow persists changes', async ({ app }) => {
    const workflowName = buildUniqueName('v2-edit-persist')
    await app.goto(toAppUrl('/workflow-builder/new'))

    try {
      // Create a simple workflow
      await addManualTrigger(app)
      await addScriptNode(app, 'Original script', 'print("original")')
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/)

      // Add a second node (edit the workflow)
      await addScriptNode(app, 'Added script', 'print("added")')

      // Re-save and capture the PATCH payload
      const patchPromise = app.waitForRequest((req) => req.url().includes('/workflows/') && req.method() === 'PATCH')
      await app.getByRole('button', { name: 'Save' }).click()
      const patchRequest = await patchPromise
      const editedDef = getV2DefFromRequest(patchRequest)

      // Verify the edited definition retains v2 structure
      expectV2SchemaStructure(editedDef)

      // Both original and added nodes should be in the definition
      expect(editedDef.nodes.length).toBeGreaterThanOrEqual(2)
      const nodeNames = editedDef.nodes.map((n) => n.name)
      expect(nodeNames).toContain('Original script')
      expect(nodeNames).toContain('Added script')

      // Edges should connect trigger → original → added
      expect(editedDef.edges.length).toBeGreaterThanOrEqual(2)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  // -------------------------------------------------------------------------
  // 7. Edges with ports persist after reload
  // -------------------------------------------------------------------------

  test('edges with from_port persist after page reload', async ({ app }) => {
    const workflowName = buildUniqueName('v2-edge-ports')
    await app.goto(toAppUrl('/workflow-builder/new'))

    try {
      // Create a workflow with a condition node (produces true/false port edges)
      await addManualTrigger(app)
      await addConditionNodeWithBranch(app, 'Branch check')

      // Save
      const savePromise = app.waitForRequest((req) => req.url().includes('/workflows') && req.method() === 'POST')
      await selectProjectIfRequired(app)
      await app.getByPlaceholder('Workflow name').fill(workflowName)
      await app.getByRole('button', { name: 'Save' }).click()
      const saveRequest = await savePromise
      const savedDef = getV2DefFromRequest(saveRequest)

      // Verify the saved definition has port-based edges
      expectV2SchemaStructure(savedDef)
      const conditionEdges = savedDef.edges.filter((e) => e.from_port === 'true' || e.from_port === 'false')
      expect(conditionEdges.length).toBeGreaterThanOrEqual(1)

      // Navigate away and reload the workflow
      await expect(app).toHaveURL(/workflow-builder\/(?!new)/)
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      // Intercept the GET response to verify edges are preserved
      let reloadedBody: unknown = null
      await app.route('**/workflows/*', async (route) => {
        if (route.request().method() !== 'GET') {
          await route.continue()
          return
        }
        const response = await route.fetch()
        reloadedBody = await response.json()
        await route.fulfill({ response })
      })

      await app.getByRole('link', { name: workflowName, exact: true }).click()
      await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName, { timeout: 30000 })
      await app.unroute('**/workflows/*')

      // Verify port-based edges survived the round-trip
      expect(reloadedBody).not.toBeNull()
      const reloadedDef = getV2DefFromResponse(reloadedBody)
      expectV2SchemaStructure(reloadedDef)

      const reloadedCondEdges = reloadedDef.edges.filter((e) => e.from_port === 'true' || e.from_port === 'false')
      expect(reloadedCondEdges.length).toBeGreaterThanOrEqual(1)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
