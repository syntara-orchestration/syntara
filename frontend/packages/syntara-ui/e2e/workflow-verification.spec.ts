/**
 * E2E tests for workflow verification, publish blocking, and error indicators.
 *
 * Covers:
 *   - Verify button in toolbar
 *   - Validation error panel with Go to node
 *   - Error/warning indicators on canvas nodes
 *   - Block publish when validation errors exist
 *   - Save with warnings
 *   - Variable reference validation errors
 */

import AxeBuilder from '@axe-core/playwright'

import { type Page } from './fixtures'
import { test, expect } from './fixtures'
import { WCAG_TAGS } from './fixtures/accessibility'
import { triggerVerifyWorkflow, VALIDATE_ROUTE } from './helpers/workflow-verify'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  createWorkflowWithTrigger,
  addScriptNode,
  addScriptNodeUnconnected,
  deleteWorkflow,
} from './helpers/workflows'
import { deleteWorkflowViaApi } from './utils/api'

const VERIFY_BANNER_TIMEOUT = 20_000
const ERROR_BADGE_TIMEOUT = 5_000
const SAVE_URL_TIMEOUT = 15_000

function getWorkflowIdFromUrl(app: Page): string {
  const id = app.url().match(/workflow-builder\/([^/?]+)/)?.[1]
  expect(id).toBeTruthy()
  return id!
}

type MockFinding = { message: string; node_id?: string | null; severity?: string; category?: string }

type MockValidateOptions = {
  valid?: boolean
  errors?: Array<{ message: string; node_id?: string | null }>
  warnings?: Array<{ message: string; node_id?: string | null }>
}

async function mockValidateEndpoint(app: Page, options: MockValidateOptions = {}): Promise<void> {
  const { valid = true, errors = [], warnings = [] } = options
  const findings: MockFinding[] = [
    ...errors.map((e) => ({ ...e, severity: 'error', category: 'schema_violation' })),
    ...warnings.map((w) => ({ ...w, severity: 'warning', category: 'schema_violation' })),
  ]
  const is_valid = valid && errors.length === 0
  // Drain an in-flight validate from save/load before installing the mock, or a
  // live response can overwrite mocked error state. Do not use networkidle —
  // WebSockets keep the network busy (E2E lint). Wait for the canvas, then for
  // a validate response if one is already in flight.
  await expect(app.locator('.react-flow')).toBeVisible()
  await app
    .waitForResponse((response) => response.url().includes('/api/v1/workflows/validate'), { timeout: 3_000 })
    .catch(() => undefined)
  await app.route(VALIDATE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_valid,
        error_count: errors.length,
        warning_count: warnings.length,
        findings,
      }),
    })
  )
}

test.describe('Verify button in toolbar', () => {
  test('verify action is visible in kebab menu', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-verify-visible')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Verify step')
      await openWorkflowInBuilder(app, workflowName, id)

      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await expect(app.getByRole('menuitem', { name: /verify workflow/i })).toBeVisible()

      await app.getByRole('button', { name: 'Workflow actions' }).click()
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verify displays validation errors', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-verify-errors')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Error step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Mock validation error', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })

  test('verify displays success when workflow is valid', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-verify-success')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Valid step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app)

      await triggerVerifyWorkflow(app)

      await expect(app.getByText('Workflow definition is valid')).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Validation error panel', () => {
  test('error panel shows issue count', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-error-panel')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Panel step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [
          { message: 'Missing required configuration', node_id: null },
          { message: 'Invalid connection type', node_id: null },
        ],
      })

      await triggerVerifyWorkflow(app)

      const banner = app.getByText(/Verification failed — \d+ issues? found/)
      await expect(banner).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })

  test.skip('error panel can be dismissed', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-error-dismiss')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Dismiss step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Mock validation error', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      const banner = app.getByText(/Verification failed/)
      await expect(banner).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      const alert = app.getByRole('alert')
      await alert.getByRole('button', { name: /close/i }).click()

      await expect(banner).not.toBeVisible()
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })

  test('clicking node name in error panel opens node editor', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-error-goto')
    const stepName = 'Goto step'

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, stepName)
      await openWorkflowInBuilder(app, workflowName, id)

      // Get the node ID from the canvas so the mock error references it
      const node = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: stepName })
      const nodeId = await node.getAttribute('data-id')

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Missing required configuration', node_id: nodeId }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await app.getByRole('button', { name: /alert details/i }).click()

      const nodeLink = app.getByRole('button', { name: stepName })
      await expect(nodeLink).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
      await nodeLink.click()

      await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible({
        timeout: VERIFY_BANNER_TIMEOUT,
      })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Error indicators on canvas nodes', () => {
  test('validation error badge appears on nodes with errors', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-error-badge')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Badge step')
      await openWorkflowInBuilder(app, workflowName, id)

      // Get the node ID so the mock error is attributed to a specific node
      const node = app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: 'Badge step' })
      const nodeId = await node.getAttribute('data-id')

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Mock validation error', node_id: nodeId }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await expect(app.locator('[data-testid="validation-error-badge"]')).toHaveCount(1, {
        timeout: ERROR_BADGE_TIMEOUT,
      })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Block publish when validation errors exist', () => {
  test('publish button is disabled when validation errors exist', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-publish-blocked')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Blocked step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Mock validation error', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      const publishButton = app.getByRole('button', { name: /publish workflow/i })
      await expect(publishButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })

  test('publish button works when workflow is valid', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-publish-clean')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Clean step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app)

      const publishButton = app.getByRole('button', { name: /publish workflow/i })
      await expect(publishButton).not.toHaveAttribute('aria-disabled', 'true')
      await publishButton.click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
      await expect(dialog.getByText('Publish workflow?')).toBeVisible()

      await dialog.getByRole('button', { name: 'Cancel' }).click()
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Save with warnings', () => {
  test('warnings are non-blocking for save and show warning banner', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-save-warnings')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'Warn step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        warnings: [{ message: 'Step has no downstream consumers', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      const warningBanner = app.getByText(/Saved with 1 warning/)
      await expect(warningBanner).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await expect(app.getByText(/Verification failed/)).not.toBeVisible()
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Variable reference validation', () => {
  test('reference to nonexistent node shows validation error', { tag: ['@konflux-skip'] }, async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-varref-invalid')

    await createWorkflowWithTrigger(app, workflowName)
    const workflowId = getWorkflowIdFromUrl(app)

    try {
      await addScriptNode(app, 'Ref step', 'echo ${nonexistent_node.result}')

      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: SAVE_URL_TIMEOUT })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await app.getByRole('button', { name: /alert details/i }).click()
      await expect(app.getByText(/does not exist in this workflow/i)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test.skip('reference to existing node that is not upstream shows validation error', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-varref-upstream')

    await createWorkflowWithTrigger(app, workflowName)
    const workflowId = getWorkflowIdFromUrl(app)

    try {
      await addScriptNode(app, 'Upstream step', 'echo hello')

      const upstreamNode = app
        .locator('[role="group"][aria-roledescription="node"]')
        .filter({ hasText: 'Upstream step' })
      const upstreamNodeId = await upstreamNode.getAttribute('data-id')

      await addScriptNodeUnconnected(app, 'Isolated step', `echo \${${upstreamNodeId}.result}`)

      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: SAVE_URL_TIMEOUT })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await app.getByRole('button', { name: /alert details/i }).click()
      await expect(app.getByText(/is not upstream of this step/i)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await deleteWorkflowViaApi(app, workflowId)
    }
  })

  test('reference to undefined input field shows validation error', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-varref-field')

    await createWorkflowWithTrigger(app, workflowName)
    const workflowId = getWorkflowIdFromUrl(app)

    try {
      await addScriptNode(app, 'Field ref step', 'echo ${input.missing_field}')

      await app.getByRole('button', { name: 'Save' }).click()
      await expect(app).toHaveURL(/workflow-builder\/.+/, { timeout: SAVE_URL_TIMEOUT })

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: '"missing_field" is not a defined input field on this trigger', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      await app.getByRole('button', { name: /alert details/i }).click()
      await expect(app.getByText(/^".*" is not a defined input field/i)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})

test.describe('Accessibility', () => {
  test.skip('verification error panel has no accessibility violations', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-accessibility-verify')

    try {
      const { id } = await createBasicWorkflowViaApi(app, workflowName, 'A11y step')
      await openWorkflowInBuilder(app, workflowName, id)

      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Mock validation error', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })

      const results = await new AxeBuilder({ page: app }).withTags([...WCAG_TAGS]).analyze()
      expect(results.violations).toEqual([])
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflow(app, workflowName)
    }
  })
})

test.describe('Empty workflow verification', () => {
  test('verify detects issues in trigger-only workflow', async ({ app }) => {
    test.setTimeout(90_000)
    const workflowName = buildUniqueName('e2e-verify-empty')

    await createWorkflowWithTrigger(app, workflowName)
    const workflowId = getWorkflowIdFromUrl(app)

    try {
      await mockValidateEndpoint(app, {
        valid: false,
        errors: [{ message: 'Workflow must have at least one action step', node_id: null }],
      })

      await triggerVerifyWorkflow(app)

      await expect(app.getByText(/Verification failed/)).toBeVisible({ timeout: VERIFY_BANNER_TIMEOUT })
    } finally {
      await app.unroute(VALIDATE_ROUTE)
      await deleteWorkflowViaApi(app, workflowId)
    }
  })
})
