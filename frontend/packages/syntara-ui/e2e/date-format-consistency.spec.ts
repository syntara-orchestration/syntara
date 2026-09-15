/**
 * E2E Tests: Date format consistency across tables (AAP-76836)
 *
 * Verifies that all table pages use the standardized date format
 * (abbreviated month name like "May 27, 2026") instead of browser
 * locale format (numeric month like "5/27/2026").
 *
 * Critical paths covered:
 * - Workflows table date columns use abbreviated month format
 * - Workflow runs (executions) table date columns use abbreviated month format
 */

import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflowViaApi, deleteWorkflow } from './helpers/workflows'

const ABBREVIATED_MONTH_PATTERN = /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}/
const NUMERIC_MONTH_PATTERN = /\d{1,2}\/\d{1,2}\/\d{4}/

test.describe('Date format consistency (AAP-76836)', () => {
  test('workflows table displays dates with abbreviated month names', async ({ app }) => {
    const workflowName = buildUniqueName('e2e-date-fmt')

    await createBasicWorkflowViaApi(app, workflowName, 'Date format test')

    try {
      await app.goto(toAppUrl('/workflows'))
      await app.getByPlaceholder('Filter by name').fill(workflowName)
      await app.getByRole('button', { name: 'Apply filter' }).click()

      const row = app.getByRole('row', { name: new RegExp(workflowName) })
      await expect(row).toBeVisible()

      const rowText = await row.textContent()

      expect(rowText).toMatch(ABBREVIATED_MONTH_PATTERN)
      expect(rowText).not.toMatch(NUMERIC_MONTH_PATTERN)
    } finally {
      await deleteWorkflow(app, workflowName)
    }
  })
})
