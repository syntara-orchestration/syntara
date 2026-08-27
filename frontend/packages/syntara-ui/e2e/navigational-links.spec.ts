import { test, expect, toAppUrl } from './fixtures'
import { createTestCredential, deleteCredentialByName, goToCredentialsList } from './helpers/credentials'

test.describe('Navigational link affordance @pr-check', () => {
  test.describe('Credentials table', () => {
    test('credential name is a navigational link', async ({ app }) => {
      const { name } = await createTestCredential(app, { prefix: 'e2e-link' })
      try {
        await goToCredentialsList(app)

        // The credential name must render as an anchor link (SynLink renders <a> via TanStack Router),
        // not as plain text — verifies proper anchor semantics and PatternFly underline affordance.
        // Scoped to [data-label="Name"] to avoid matching the kebab "Actions for <name>" toggle.
        const credLink = app.locator('[data-label="Name"]').getByRole('link', { name })
        await expect(credLink).toBeVisible()

        // Clicking it must navigate to the credential detail page.
        await credLink.click()
        await expect(app).toHaveURL(/\/configuration\/credentials\//)
        await expect(app.locator('h1').filter({ hasText: name })).toBeVisible()
      } finally {
        await deleteCredentialByName(app, name)
      }
    })
  })

  test.describe('Workflows table', () => {
    test('workflow name is a navigational link', async ({ app }) => {
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      // The workflow name column uses dataLabel="Name". We scope directly to that column
      // to skip over project group header rows (which have a colSpan cell and no name cell).
      // Against a real backend with no seed data there will be no name cells at all.
      const nameLinks = app.locator('[data-label="Name"]').getByRole('link')
      const linkCount = await nameLinks.count()
      test.skip(linkCount === 0, 'No workflows available — defensive guard for unseeded real backends')

      // The workflow name cell must contain an anchor link, not plain text.
      // eslint-disable-next-line no-restricted-properties -- multiple workflow links are expected; .first() is intentional here (no-nth-in-e2e rule replaces no-restricted-properties)
      const firstWorkflowLink = nameLinks.first()
      await expect(firstWorkflowLink).toBeVisible()

      // Clicking it must navigate to the workflow builder.
      await firstWorkflowLink.click()
      await expect(app).toHaveURL(/\/workflow-builder\//)
    })
  })

  test.describe('Workflow Runs table', () => {
    test('run ID is a navigational link', async ({ app }) => {
      await app.goto(toAppUrl('/executions'))
      await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

      // Against a real backend with no executions the table would be empty.
      // Skipping is acceptable because: (a) this test only verifies link affordance,
      // not execution creation, and (b) executions.spec.ts covers creation end-to-end.
      const runLinks = app.getByRole('table').locator('[data-label="Run ID"]').getByRole('link')
      const linkCount = await runLinks.count()
      test.skip(linkCount === 0, 'No workflow runs available — defensive guard for unseeded real backends')

      // The run ID cell must contain an anchor link, not plain text.
      // eslint-disable-next-line no-restricted-properties -- multiple run-ID links are expected; .first() is intentional here (no-nth-in-e2e rule replaces no-restricted-properties)
      const firstRunLink = runLinks.first()
      await expect(firstRunLink).toBeVisible()

      // Clicking it must navigate to the execution detail page.
      await firstRunLink.click()
      await expect(app).toHaveURL(/\/executions\//)
    })
  })
})
