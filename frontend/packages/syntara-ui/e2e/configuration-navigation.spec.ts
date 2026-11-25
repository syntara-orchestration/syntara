import { test, expect, toAppUrl } from './fixtures'
import { expectDockedNavGroupChildLinks, mainNavigation, navigateViaConfigurationMenu } from './helpers/docked-nav'

test.describe('Configuration Navigation & Tabs', () => {
  test('displays all Configuration sub-navigation tabs', async ({ app }) => {
    // Navigate to a stable page so the router has fully settled before touching the nav.
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    await expectDockedNavGroupChildLinks(app, 'Configuration', ['Integrations', 'Credentials'], 'Integrations')
  })

  test('navigates to Credentials page from Configuration menu', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    await navigateViaConfigurationMenu(app, 'Credentials')

    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
  })

  test('persists active tab after page refresh', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/credentials'))
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

    await app.reload()

    await expect(mainNavigation(app)).toBeVisible()
    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
  })

  test('navigates between all Configuration tabs successfully', async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()

    await navigateViaConfigurationMenu(app, 'Credentials')
    await expect(app).toHaveURL(/configuration\/credentials/)
    await expect(app.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

    await navigateViaConfigurationMenu(app, 'Integrations')
    await expect(app).toHaveURL(/configuration\/integrations/)
    await expect(app.getByRole('heading', { name: 'Integrations', level: 1 })).toBeVisible()
  })
})
