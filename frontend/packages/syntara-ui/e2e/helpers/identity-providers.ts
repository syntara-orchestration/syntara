import { expect, type Page, toAppUrl } from '../fixtures'

const AUTH_ROOT = '/system-administration/authentication'
const ADD_IDP_URL = `${AUTH_ROOT}/identity-providers/add`

/** Minimal OIDC configuration for API-created providers in mapping E2E tests. */
export const MINIMAL_OIDC_PROVIDER_CONFIGURATION = {
  provider_type: 'oidc' as const,
  idp_type: 'custom',
  auto_discovery: true,
  issuer_url: 'https://idp.example.com',
  client_id: 'e2e-client-id',
  redirect_uri: 'http://localhost/callback',
  scopes: 'openid profile email',
}

export function identityProviderDetailUrl(providerId: string, tab: 'details' | 'group-mapping' = 'details'): string {
  return `${AUTH_ROOT}/identity-providers/${providerId}/${tab}`
}

export function identityProviderGroupMappingEditUrl(providerId: string, query?: string): string {
  const base = `${AUTH_ROOT}/identity-providers/${providerId}/group-mapping/edit`
  return query ? `${base}?${query}` : base
}

/** Navigate to the identity providers list. */
export async function gotoIdentityProvidersList(app: Page): Promise<void> {
  await app.goto(toAppUrl(AUTH_ROOT))
  await expect(app.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
}

/** Navigate to an identity provider detail tab. */
export async function gotoIdentityProviderDetail(
  app: Page,
  providerId: string,
  tab: 'details' | 'group-mapping' = 'details'
): Promise<void> {
  await app.goto(toAppUrl(identityProviderDetailUrl(providerId, tab)))
  await expect(app.getByRole('tab', { name: /Group mapping/i })).toBeVisible({ timeout: 15_000 })
  if (tab === 'group-mapping') {
    await expect(app.getByRole('tab', { name: /Group mapping/i })).toHaveAttribute('aria-selected', 'true')
    await expect(
      app.getByRole('button', { name: /Add manually/i }).or(app.getByRole('button', { name: /Edit group mapping/i }))
    ).toBeVisible({ timeout: 15_000 })
  }
}

/** Open the Add OIDC provider wizard on the provider configuration step. */
export async function gotoAddOidcProviderWizard(app: Page): Promise<void> {
  await gotoIdentityProvidersList(app)
  await app.getByRole('button', { name: /Add OIDC provider/i }).click()
  await expect(app.getByRole('heading', { level: 1, name: 'Add OIDC provider' })).toBeVisible()
}

/** Select the Custom provider template on the add-provider wizard. */
export async function selectCustomProviderTemplate(app: Page): Promise<void> {
  await app.getByRole('button', { name: /Select a provider template/i }).click()
  const listbox = app.getByRole('listbox')
  await expect(listbox).toBeVisible()
  await listbox.getByRole('option', { name: /^Custom$/i }).click()
}

/** Fill minimal required OIDC fields on step 1 of the add-provider wizard. */
export async function fillMinimalOidcProviderFields(
  app: Page,
  options: { name: string; issuerUrl?: string; clientId?: string; clientSecret?: string }
): Promise<void> {
  await selectCustomProviderTemplate(app)

  await app.getByRole('textbox', { name: /Provider name/i }).fill(options.name)

  const enabledToggle = app.getByRole('switch', { name: /Enabled/ })
  await expect(enabledToggle).toBeVisible()
  await enabledToggle.click({ force: true })

  await app
    .getByRole('textbox', { name: /Issuer URL/i })
    .fill(options.issuerUrl ?? 'https://keycloak.example.com/realms/test')
  await app.getByRole('textbox', { name: /Client ID/i }).fill(options.clientId ?? 'e2e-client-id')
  await app.getByRole('textbox', { name: /Client secret/i }).fill(options.clientSecret ?? 'e2e-client-secret')
}

/** Go to the Claim mapping wizard step. */
export async function gotoClaimMappingWizardStep(app: Page): Promise<void> {
  await app.getByRole('button', { name: /Claim mapping/i }).click()
  await expect(app.getByText('Subject claim')).toBeVisible()
}

/** Open the dedicated group mapping form (via Add manually or Edit group mapping on the tab). */
export async function enterGroupMappingEditMode(app: Page): Promise<void> {
  const addManually = app.getByRole('button', { name: /Add manually/i })
  const fromEmptyState = await addManually.isVisible()
  if (fromEmptyState) {
    await addManually.click()
  } else {
    await app.getByRole('button', { name: /Edit group mapping/i }).click()
  }
  const expectedHeading = fromEmptyState ? 'Add group mapping' : 'Edit group mapping'
  await expect(app.getByRole('heading', { level: 1, name: expectedHeading })).toBeVisible()
  await expect(app.getByRole('button', { name: /Save mapping/i })).toBeVisible()
}

/** Navigate directly to the group mapping edit form. */
export async function gotoGroupMappingEdit(app: Page, providerId: string, query?: string): Promise<void> {
  await app.goto(toAppUrl(identityProviderGroupMappingEditUrl(providerId, query)))
  await expect(app.getByRole('button', { name: /Save mapping/i })).toBeVisible({ timeout: 15_000 })
}

/** Expand the Advanced section on the group mapping tab. */
export async function expandGroupMappingAdvanced(app: Page): Promise<void> {
  await app.getByRole('button', { name: /^Advanced$/i }).click()
  await expect(app.getByRole('textbox', { name: 'Group extraction expression', exact: true })).toBeVisible()
}

export { ADD_IDP_URL, AUTH_ROOT }
