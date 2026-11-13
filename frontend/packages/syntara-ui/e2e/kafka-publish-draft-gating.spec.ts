/** Kafka draft gating across first save/navigation and reload, using advisory-save API responses. */
import type { WorkflowAPI } from '@syntara/contracts'
import { z } from 'zod'

import { expect, test, toAppUrl, type Page } from './fixtures'
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

const definitionSchema = z.looseObject({
  nodes: z.array(z.looseObject({ id: z.string(), type: z.string(), parameters: z.record(z.string(), z.unknown()) })),
})

function validationFor(
  definition: z.infer<typeof definitionSchema>
): WorkflowAPI.components['schemas']['ValidationResult'] {
  const findings: WorkflowAPI.components['schemas']['ValidationFinding'][] = []
  for (const node of definition.nodes.filter((node) => node.type === 'kafka_publish')) {
    for (const field of ['integration_id', 'credential_id', 'topic', 'payload']) {
      if (node.parameters[field] !== undefined && node.parameters[field] !== '') continue
      findings.push({
        severity: 'error',
        category: 'missing_field',
        node_id: node.id,
        field_path: `parameters.${field}`,
        message: field === 'payload' ? 'JSON payload is required' : `${field} is required`,
      })
    }
  }
  return { is_valid: findings.length === 0, error_count: findings.length, warning_count: 0, findings }
}

async function mockAdvisorySaves(app: Page) {
  // Keep the real mock API's persistence; supply the production advisory validation contract.
  await app.route(/\/api\/v1\/workflows(?:\/[^/?]+)?(?:\?.*)?$/, async (route) => {
    const request = route.request()
    const method = request.method()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/validate')) {
      const body: unknown = request.postDataJSON()
      const { workflow_definition: definition } = z.object({ workflow_definition: definitionSchema }).parse(body)
      await route.fulfill({ json: validationFor(definition) })
      return
    }
    if (!['GET', 'POST', 'PATCH'].includes(method)) return route.continue()
    const response = await route.fetch()
    const body: unknown = await response.json()
    const data = z
      .looseObject({
        version: z.looseObject({ workflow_definition: definitionSchema }).optional(),
      })
      .parse(body)
    const isSave = method === 'POST' || method === 'PATCH'
    const requestBody: unknown = isSave ? request.postDataJSON() : undefined
    const definition = isSave
      ? z.object({ workflow_definition: definitionSchema }).parse(requestBody).workflow_definition
      : data.version?.workflow_definition
    if (!definition) return route.fulfill({ response })
    const validation = validationFor(definition)
    const json = {
      ...data,
      has_validation_issues: !validation.is_valid,
      ...(isSave && { validation_result: validation }),
    }
    // Production create responses omit the version; the builder must load it after navigating.
    if (method === 'POST') delete json.version
    await route.fulfill({ response, json })
  })
}

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
    if (!isSkipWebServerForPlaywrightTests()) await mockAdvisorySaves(app)
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
      await expect(app.getByText('JSON payload is required', { exact: true })).toBeVisible()
    }
  } finally {
    if (workflowId) await deleteWorkflowViaApi(app, workflowId)
    await deleteProjectViaApi(app, project.id)
  }
})
