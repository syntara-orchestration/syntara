import { test, expect, type Page, toAppUrl } from './fixtures'
import { gotoAddOidcProviderWizard } from './helpers/identity-providers'
import { buildUniqueName } from './helpers/workflows'

const AUTHENTICATION_URL = '/system-administration/authentication'
const ADD_PROVIDER_URL = `${AUTHENTICATION_URL}/identity-providers/add`

async function openDirtyAddProviderForm(app: Page): Promise<string> {
  await gotoAddOidcProviderWizard(app)
  const providerName = buildUniqueName('oidc-cancel')
  await app.getByRole('textbox', { name: /Provider name/i }).fill(providerName)
  return providerName
}

test.describe('Add OIDC provider Cancel navigation', () => {
  test('ordinary click keeps the unsaved changes guard', async ({ app }) => {
    const providerName = await openDirtyAddProviderForm(app)

    await app.getByRole('link', { name: 'Cancel', exact: true }).click()

    const discardDialog = app.getByRole('dialog')
    await expect(discardDialog).toBeVisible()
    await expect(discardDialog.getByRole('heading', { name: /Discard unsaved changes/ })).toBeVisible()
    await expect(app).toHaveURL(toAppUrl(ADD_PROVIDER_URL))

    await discardDialog.getByRole('button', { name: 'Cancel' }).click()

    await expect(discardDialog).not.toBeVisible()
    await expect(app.getByRole('heading', { level: 1, name: 'Add OIDC provider' })).toBeVisible()
    await expect(app.getByRole('textbox', { name: /Provider name/i })).toHaveValue(providerName)
  })

  test('modified click opens authentication in a new tab and preserves the form', async ({ app }) => {
    const providerName = await openDirtyAddProviderForm(app)
    const cancelLink = app.getByRole('link', { name: 'Cancel', exact: true })
    await expect(cancelLink).toHaveAttribute('href', AUTHENTICATION_URL)

    const openedPagePromise = app.context().waitForEvent('page')
    await cancelLink.click({ modifiers: ['ControlOrMeta'] })
    const authenticationPage = await openedPagePromise

    await expect(authenticationPage).toHaveURL(toAppUrl(AUTHENTICATION_URL))
    await expect(authenticationPage.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
    await expect(app).toHaveURL(toAppUrl(ADD_PROVIDER_URL))
    await expect(app.getByRole('heading', { level: 1, name: 'Add OIDC provider' })).toBeVisible()
    await expect(app.getByRole('textbox', { name: /Provider name/i })).toHaveValue(providerName)
    await expect(app.getByRole('dialog')).not.toBeVisible()

    await authenticationPage.close()
  })
})
