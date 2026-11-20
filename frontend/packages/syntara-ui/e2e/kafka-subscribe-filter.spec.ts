import { readFile } from 'node:fs/promises'

import AxeBuilder from '@axe-core/playwright'

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, clickSaveAndWait, fillCodeEditor, openNodeForEditing } from './helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from './utils/api'

const EXPRESSION = 'Filter expression (CEL)'
const SAMPLE = 'Sample JSON'
const TEST_FILTER = 'Test filter'
const EXACT_SOURCE = '  (input.key.kind == "text")\n && (true || false)  '

const FILTER_TEST_RESULTS: Record<string, { outcome: string; error_code?: string }> = {
  true: { outcome: 'match' },
  false: { outcome: 'no_match' },
  'input.missing': { outcome: 'no_match' },
  input: { outcome: 'evaluation_error', error_code: 'filter_non_boolean' },
}

function filterExpression(payload: unknown): string {
  if (typeof payload !== 'object' || payload === null || !('expression' in payload)) return ''
  return typeof payload.expression === 'string' ? payload.expression : ''
}

test.describe('Kafka Subscribe CEL filter', () => {
  test('describes the actual sample editor in inline and expanded modes', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await app.getByRole('button', { name: 'Kafka Subscribe trigger', exact: true }).click()
    await app.getByRole('button', { name: 'Test filter expression', exact: true }).click()
    const hint = /The sample is bound directly as input, without a wrapper or Kafka decoding/
    const sample = app.getByRole('textbox', { name: /^Sample JSON/ })
    await expect(sample).toHaveAccessibleDescription(hint)
    await sample.focus()
    await expect(sample).toBeFocused()
    await app.getByRole('button', { name: 'Open in new window', exact: true }).click()
    const dialog = app.getByRole('dialog', { name: 'Edit sample JSON modal', exact: true })
    const expanded = dialog.getByRole('textbox', { name: /^Sample JSON expanded/ })
    await expect(expanded).toHaveAccessibleDescription(hint)
    await expanded.focus()
    await expect(expanded).toBeFocused()
    const results = await new AxeBuilder({ page: app })
      .include('[role="dialog"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(results.violations).toEqual([])
    await app.keyboard.press('Escape')
    await expect(sample).toHaveAccessibleDescription(hint)
  })

  test('tests unsaved input without Kafka resources and distinguishes validation and evaluation outcomes', async ({
    app,
  }, testInfo) => {
    // Konflux deploys the devel API, which does not serve this route.
    await app.route('**/api/v1/filtering/test', async (route) => {
      const expression = filterExpression(route.request().postDataJSON())
      if (expression === 'input.') {
        await route.fulfill({
          status: 422,
          contentType: 'application/problem+json',
          body: JSON.stringify({
            type: 'https://api.example.com/errors/validation-error',
            title: 'Invalid CEL filter expression',
            detail: 'filter_invalid_syntax',
            code: 'filter_invalid_syntax',
            retryable: false,
            line: 1,
            column: 7,
          }),
        })
        return
      }
      await route.fulfill({
        json: FILTER_TEST_RESULTS[expression.trim()] ?? {
          outcome: 'evaluation_error',
          error_code: 'filter_evaluation_failed',
        },
      })
    })
    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await app.getByRole('button', { name: 'Kafka Subscribe trigger', exact: true }).click()
      const editor = app.getByRole('textbox', { name: EXPRESSION })
      await expect(editor).toHaveValue('')
      await editor.fill('true')
      await app.getByRole('button', { name: 'Test filter expression', exact: true }).scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-filter-prototype-aligned.png'), fullPage: true })
      await app.getByRole('button', { name: 'More info for Filter expression (CEL)', exact: true }).click()
      await expect(app.getByRole('link', { name: 'Kafka Subscribe documentation' })).toBeVisible()
      await expect(app.getByText(/Return true to pass a message/)).toBeVisible()
      await app.keyboard.press('Escape')
      await editor.focus()
      await app.keyboard.press('Tab')
      await expect(app.getByRole('button', { name: 'Test filter expression', exact: true })).toBeFocused()
      await app.keyboard.press('Enter')
      await expect(app.getByRole('button', { name: 'Hide filter test', exact: true })).toBeFocused()
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Success alert: Match', exact: true })).toBeVisible()
      await editor.fill('false')
      await expect(app.getByRole('heading', { name: 'Success alert: Match', exact: true })).toBeHidden()
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Info alert: No match', exact: true })).toBeVisible()
      await editor.fill('input.missing')
      await expect(app.getByRole('heading', { name: 'Info alert: No match', exact: true })).toBeHidden()
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Info alert: No match', exact: true })).toBeVisible()
      await editor.fill('input')
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Warning alert: Evaluation error', exact: true })).toBeVisible()
      await expect(
        app.getByText('This expression must return true or false. Update the expression and test again.')
      ).toBeVisible()
      await editor.fill('input.')
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(
        app.getByRole('heading', { name: 'Danger alert: Filter configuration error', exact: true })
      ).toBeVisible()
      await expect(editor).toHaveValue('input.')
      await expect(editor).toHaveAccessibleDescription(/Syntax error at line 1, column 7/)
      await editor.scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-cel-filter-configuration-error.png'), fullPage: true })
      await editor.fill('true')
      await fillCodeEditor(app, { label: SAMPLE, value: '{' })
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByText('Enter valid JSON before testing the filter')).toBeVisible()
      await fillCodeEditor(app, { label: SAMPLE, value: 'null' })
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Success alert: Match', exact: true })).toBeVisible()
      await app.getByRole('heading', { name: 'Success alert: Match', exact: true }).scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-cel-filter-match.png'), fullPage: true })
      const results = await new AxeBuilder({ page: app })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze()
      expect(results.violations).toEqual([])
      await editor.clear()
      await expect(editor).toBeFocused()
      await app.getByRole('button', { name: 'Hide filter test', exact: true }).click()
      await expect(app.getByRole('button', { name: 'Test filter expression', exact: true })).toBeFocused()
    } finally {
      await app.unroute('**/api/v1/filtering/test')
    }
  })

  test('retains invalid source after rejected save, then preserves corrected source through unrelated edits and removal', async ({
    app,
  }) => {
    const { id } = await createWorkflowViaApi({
      app,
      name: buildUniqueName('kafka-cel'),
      triggers: [
        { id: 'kafka_trigger', name: 'Kafka orders', type: 'event_subscribe_trigger', parameters: { filter: null } },
      ],
    })
    try {
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await openNodeForEditing(app, 'Kafka orders')
      await app.getByRole('textbox', { name: EXPRESSION }).fill('input.')
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      await app.route(`**/api/v1/workflows/${id}`, async (route) => {
        if (route.request().method() !== 'PATCH') return route.continue()
        await route.fulfill({
          status: 422,
          contentType: 'application/problem+json',
          body: JSON.stringify({
            code: 'WORKFLOW_DEFINITION_INVALID',
            title: 'Invalid workflow',
            detail: 'Invalid filter configuration',
            validation_result: {
              findings: [
                {
                  node_id: 'kafka_trigger',
                  field_path: 'parameters.filter.expression',
                  message: 'CEL filter: Syntax error at line 1, column 7.',
                  severity: 'error',
                },
              ],
            },
          }),
        })
      })
      const rejection = app.waitForResponse(
        (response) => response.status() === 422 && response.request().method() === 'PATCH'
      )
      await app.getByRole('button', { name: 'Save workflow', exact: true }).click()
      expect((await rejection).request().postDataJSON()).toMatchObject({
        workflow_definition: { triggers: [{ parameters: { filter: { expression: 'input.' } } }] },
      })
      await app.getByRole('button', { name: 'Danger alert details', exact: true }).click()
      await expect(app.getByText('CEL filter: Syntax error at line 1, column 7.', { exact: true })).toBeVisible()
      await openNodeForEditing(app, 'Kafka orders')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveValue('input.')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveAccessibleDescription(
        /Syntax error at line 1, column 7/
      )
      await app.getByRole('textbox', { name: EXPRESSION }).fill(EXACT_SOURCE)
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      await app.unroute(`**/api/v1/workflows/${id}`)
      await clickSaveAndWait(app)
      await app.reload()
      await openNodeForEditing(app, 'Kafka orders')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveValue(EXACT_SOURCE)
      await app.getByRole('textbox', { name: 'Topic', exact: true }).fill('orders.qa')
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      await clickSaveAndWait(app)
      await app.reload()
      await openNodeForEditing(app, 'Kafka orders')
      await expect(app.getByRole('textbox', { name: 'Topic', exact: true })).toHaveValue('orders.qa')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveValue(EXACT_SOURCE)
      await app.getByRole('textbox', { name: EXPRESSION }).clear()
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      const saved = app.waitForResponse(
        (response) => response.request().method() === 'PATCH' && response.url().endsWith(`/workflows/${id}`)
      )
      await clickSaveAndWait(app)
      const body: unknown = (await saved).request().postDataJSON()
      expect(body).toMatchObject({ workflow_definition: { triggers: [{ parameters: { filter: null } }] } })
      await app.reload()
      await openNodeForEditing(app, 'Kafka orders')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveValue('')
    } finally {
      await deleteWorkflowViaApi(app, id)
    }
  })

  test('ignores a delayed response after editing the expression and sample', async ({ app }) => {
    let release: (() => void) | undefined
    const heldResponse = new Promise<void>((resolve) => {
      release = resolve
    })
    await app.route('**/api/v1/filtering/test', async (route) => {
      await heldResponse
      await route.fulfill({ json: { outcome: 'match' } })
    })
    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await app.getByRole('button', { name: 'Kafka Subscribe trigger', exact: true }).click()
      await app.getByRole('textbox', { name: EXPRESSION }).fill('true')
      await app.getByRole('button', { name: 'Test filter expression', exact: true }).click()
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByText('Testing filter…')).toBeVisible()
      await app.getByRole('textbox', { name: EXPRESSION }).fill('false')
      await fillCodeEditor(app, { label: SAMPLE, value: 'null' })
      const response = app.waitForResponse('**/api/v1/filtering/test')
      release?.()
      await response
      await expect(app.getByRole('heading', { name: 'Success alert: Match', exact: true })).toBeHidden()
      await expect(app.getByText('Testing filter…')).toBeHidden()
    } finally {
      release?.()
      await app.unroute('**/api/v1/filtering/test')
    }
  })

  test('exports and imports the original CEL expression without rewriting it', async ({ app }) => {
    const { id } = await createWorkflowViaApi({
      app,
      name: buildUniqueName('kafka-cel-export'),
      triggers: [
        {
          id: 'kafka_trigger',
          name: 'Kafka orders',
          type: 'event_subscribe_trigger',
          parameters: { filter: { expression: EXACT_SOURCE } },
        },
      ],
    })
    try {
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
      const downloadPromise = app.waitForEvent('download')
      await app.getByRole('menuitem', { name: 'Export workflow', exact: true }).click()
      const download = await downloadPromise
      const exported = await readFile(await download.path(), 'utf8')
      const definition: unknown = JSON.parse(exported)
      expect(definition).toMatchObject({ triggers: [{ parameters: { filter: { expression: EXACT_SOURCE } } }] })

      await app.getByRole('button', { name: 'Workflow actions', exact: true }).click()
      await app.getByRole('menuitem', { name: 'Import workflow', exact: true }).click()
      await app.locator('input[type="file"][accept=".json"]').setInputFiles({
        name: 'kafka-filter.json',
        mimeType: 'application/json',
        buffer: Buffer.from(exported),
      })
      const dialog = app.getByRole('dialog', { name: 'Import workflow?' })
      await dialog.getByRole('radio', { name: /Import into current workflow/ }).click()
      await dialog.getByRole('button', { name: 'Import workflow', exact: true }).click()
      await expect(dialog).toBeHidden()
      await openNodeForEditing(app, 'Kafka orders')
      await expect(app.getByRole('textbox', { name: EXPRESSION })).toHaveValue(EXACT_SOURCE)
    } finally {
      await deleteWorkflowViaApi(app, id)
    }
  })

  test('shows Verify findings beside the filter and clears field feedback on correction', async ({ app }, testInfo) => {
    const { id } = await createWorkflowViaApi({
      app,
      name: buildUniqueName('kafka-verify'),
      triggers: [
        {
          id: 'kafka_trigger',
          name: 'Kafka validation',
          type: 'event_subscribe_trigger',
          parameters: { filter: null },
        },
      ],
    })
    await app.route('**/api/v1/workflows/validate', (route) =>
      route.fulfill({
        json: {
          is_valid: false,
          error_count: 1,
          warning_count: 0,
          findings: [
            {
              severity: 'error',
              category: 'schema_violation',
              node_id: 'kafka_trigger',
              field_path: 'parameters.filter.expression',
              message: 'CEL filter: Syntax error at line 1, column 7.',
            },
          ],
        },
      })
    )
    try {
      await app.goto(toAppUrl(`/workflow-builder/${id}`))
      await openNodeForEditing(app, 'Kafka validation')
      await app.getByRole('textbox', { name: EXPRESSION }).fill('input.')
      await app.getByRole('button', { name: 'Update', exact: true }).click()
      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: 'Verify workflow' }).click()
      await app.getByRole('button', { name: 'Danger alert details', exact: true }).click()
      await expect(app.getByText('CEL filter: Syntax error at line 1, column 7.', { exact: true })).toBeVisible()
      await openNodeForEditing(app, 'Kafka validation')
      const editor = app.getByRole('textbox', { name: EXPRESSION })
      await expect(editor).toHaveValue('input.')
      await expect(editor).toHaveAccessibleDescription(/Syntax error at line 1, column 7/)
      await editor.scrollIntoViewIfNeeded()
      await app.screenshot({ path: testInfo.outputPath('kafka-verify-filter-field-error.png'), fullPage: true })
      await editor.fill('true')
      await expect(editor).toHaveAttribute('aria-invalid', 'false')
    } finally {
      await app.unroute('**/api/v1/workflows/validate')
      await deleteWorkflowViaApi(app, id)
    }
  })

  test('uses compact request feedback and retries with the existing Test filter action', async ({ app }, testInfo) => {
    let attempts = 0
    await app.route('**/api/v1/filtering/test', (route) => {
      attempts += 1
      return attempts === 1
        ? route.fulfill({ status: 503, json: { code: 'SERVICE_UNAVAILABLE', title: 'Unavailable', retryable: true } })
        : route.fulfill({ json: { outcome: 'match' } })
    })
    try {
      await app.goto(toAppUrl('/workflow-builder/new'))
      await app.getByRole('button', { name: 'Kafka Subscribe trigger', exact: true }).click()
      await app.getByRole('textbox', { name: EXPRESSION }).fill('true')
      await app.getByRole('button', { name: 'Test filter expression', exact: true }).click()
      await app.getByRole('button', { name: 'More info for Test filter', exact: true }).click()
      await expect(app.getByText(/Sample testing does not consume Kafka messages/)).toBeVisible()
      await app.keyboard.press('Escape')
      await fillCodeEditor(app, { label: SAMPLE, value: '{"key":{"text":"order-42"}}' })
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(
        app.getByRole('heading', { name: 'Danger alert: Filter test request failed', exact: true })
      ).toBeVisible()
      await expect(app.getByRole('button', { name: 'Retry', exact: true })).toBeHidden()
      await app
        .getByRole('heading', { name: 'Danger alert: Filter test request failed', exact: true })
        .scrollIntoViewIfNeeded()
      await app.screenshot({
        path: testInfo.outputPath('kafka-filter-compact-failure-json-editor.png'),
        fullPage: true,
      })
      await app.getByRole('button', { name: TEST_FILTER, exact: true }).click()
      await expect(app.getByRole('heading', { name: 'Success alert: Match', exact: true })).toBeVisible()
      expect(attempts).toBe(2)
    } finally {
      await app.unroute('**/api/v1/filtering/test')
    }
  })
})
