import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'

async function navigateViaConfigMenu(app: Page, itemName: string) {
  await app.getByRole('button', { name: 'Configuration' }).click()
  await app.getByRole('menuitem', { name: itemName }).click()
}

test.describe('Configuration Navigation & Tabs', () => {
  test('displays all Configuration sub-navigation tabs', async ({ app }) => {
    // Navigate to a stable page so the router has fully settled before touching the nav.
    // Without this, the SPA's initial redirect from root fires mid-test and the PF6
    // flyout click gets swallowed by the re-rendering nav component.
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    // Act - Open the Configuration flyout dropdown
    const configButton = app.getByRole('button', { name: 'Configuration', exact: true })
    await configButton.click()

    // Assert - Configuration tabs are visible (Credential Types removed for GA)
    await expect(app.getByRole('menuitem', { name: 'Integrations', exact: true })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: 'Credentials', exact: true })).toBeVisible()
  })

  test('navigates to Credentials page from Configuration menu', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    // Act - Open Configuration dropdown and click Credentials
    await navigateViaConfigMenu(app, 'Credentials')

    // Assert - URL and page heading are correct
    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
  })

  test('persists active tab after page refresh', async ({ app }) => {
    // Arrange - Navigate directly to Credentials page
    await app.goto(toAppUrl('/configuration/credentials'))
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

    // Act - Reload the page
    await app.reload()

    // Assert - Route and heading persist after reload
    await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
  })

  test('navigates between all Configuration tabs successfully', async ({ app }) => {
    // Arrange - Start at Integrations page
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    // Act & Assert - Navigate to Credentials
    await navigateViaConfigMenu(app, 'Credentials')
    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

    // Act & Assert - Navigate back to Integrations (full circle)
    await navigateViaConfigMenu(app, 'Integrations')
    await expect(app).toHaveURL(/configuration\/integrations/)
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()
  })
})
