import AxeBuilder from '@axe-core/playwright'

import { type Page, test, expect, toAppUrl } from './fixtures'
import { WCAG_TAGS } from './fixtures/accessibility'

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze()
  expect(results.violations).toEqual([])
}

test.describe('Accessibility', () => {
  test('workflows page has no accessibility violations', async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

    await expectNoA11yViolations(app)
  })

  test('executions page has no accessibility violations', async ({ app }) => {
    await app.goto(toAppUrl('/executions'))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

    await expectNoA11yViolations(app)
  })

  test('approvals page has no accessibility violations', async ({ app }) => {
    await app.goto(toAppUrl('/approvals'))
    await expect(app.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()

    await expectNoA11yViolations(app)
  })

  test('integrations page has no accessibility violations', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()

    await expectNoA11yViolations(app)
  })

  test('workflow builder page has no accessibility violations', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByPlaceholder('Workflow name')).toBeVisible()

    await expectNoA11yViolations(app)
  })
})
