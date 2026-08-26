/**
 * E2E Tests: Authentication — Group mapping, JMESPath, and claim configuration
 *
 * - UI-11: Auto group mapping — configuration screen
 * - UI-12: Manual group mapping — configuration screen
 * - UI-13: JMESPath filter — entry and validation error
 * - UI-14: Claim data configuration screen
 */
import { type Page } from './fixtures'
import { test, expect } from './fixtures'
import {
  expandGroupMappingAdvanced,
  fillMinimalOidcProviderFields,
  gotoAddOidcProviderWizard,
  gotoClaimMappingWizardStep,
  gotoGroupMappingEdit,
  MINIMAL_OIDC_PROVIDER_CONFIGURATION,
} from './helpers/identity-providers'
import { buildUniqueName } from './helpers/workflows'
import { createIdentityProviderViaApi, deleteIdentityProviderViaApi, findIdentityProviderByName } from './utils/api'

const VALID_JMESPATH = "groups[?starts_with(@, 'syntara-')]"
const INVALID_JMESPATH = '[[[bad'

async function createMappingTestProvider(app: Page, namePrefix: string): Promise<string> {
  const provider = await createIdentityProviderViaApi(app, {
    name: buildUniqueName(namePrefix),
    configuration: MINIMAL_OIDC_PROVIDER_CONFIGURATION,
  })
  if (!provider?.id) {
    throw new Error(`Failed to create identity provider via API (${namePrefix})`)
  }
  return provider.id
}

async function setGroupMappingExpression(app: Page, expression: string): Promise<void> {
  await expandGroupMappingAdvanced(app)
  const expressionInput = app.getByRole('textbox', { name: 'Group extraction expression', exact: true })
  await expressionInput.fill(expression)
}

async function saveGroupMapping(app: Page): Promise<void> {
  await app.getByRole('button', { name: /Save mapping/i }).click()
}

async function selectMappedGroupForRow(app: Page, groupName: string): Promise<void> {
  const mappingRow = app.getByRole('row').filter({
    has: app.getByRole('textbox', { name: 'IdP group value 1' }),
  })
  const groupSelect = mappingRow.getByPlaceholder('Select a group...')
  await groupSelect.click()
  await groupSelect.fill(groupName)
  await app.getByRole('option', { name: new RegExp(`^${groupName}\\b`) }).click()
}

test.describe('UI-11: Auto group mapping — configuration screen', () => {
  test('saves auto group extraction expression without manual mapping rows', async ({ app }) => {
    const providerId = await createMappingTestProvider(app, 'e2e-auto-mapping')
    try {
      await gotoGroupMappingEdit(app, providerId, 'new=1')

      const removeBtn = app.getByRole('button', { name: /Remove mapping 1/i })
      if (await removeBtn.isVisible()) {
        await removeBtn.click()
      }

      await setGroupMappingExpression(app, VALID_JMESPATH)
      await saveGroupMapping(app)

      await expect(app.getByText('Group mapping saved')).toBeVisible()
      await expect(app.getByRole('heading', { name: /no group mappings configured/i })).toBeVisible()
    } finally {
      await deleteIdentityProviderViaApi(app, providerId)
    }
  })
})

test.describe('UI-12: Manual group mapping — configuration screen', () => {
  const idpGroupValue = 'platform-admins'

  test('creates manual mapping from IdP group value to Syntara group', async ({ app }) => {
    const providerId = await createMappingTestProvider(app, 'e2e-manual-mapping')
    try {
      await gotoGroupMappingEdit(app, providerId, 'new=1')

      await app.getByRole('textbox', { name: 'IdP group value 1' }).fill(idpGroupValue)
      await selectMappedGroupForRow(app, 'admins')
      await saveGroupMapping(app)

      await expect(app.getByText('Group mapping saved')).toBeVisible()
      await expect(app.getByRole('button', { name: /Edit group mapping/i })).toBeVisible()
      await expect(app.getByText(idpGroupValue)).toBeVisible()
      await expect(app.getByText('admins', { exact: true })).toBeVisible()
    } finally {
      await deleteIdentityProviderViaApi(app, providerId)
    }
  })
})

test.describe('UI-13: JMESPath filter — entry and validation error', () => {
  test.describe('Group mapping tab', () => {
    test('saves a valid JMESPath expression', async ({ app }) => {
      const providerId = await createMappingTestProvider(app, 'e2e-jmespath-tab')
      try {
        await gotoGroupMappingEdit(app, providerId)

        await setGroupMappingExpression(app, VALID_JMESPATH)
        await saveGroupMapping(app)
        await expect(app.getByText('Group mapping saved')).toBeVisible()
      } finally {
        await deleteIdentityProviderViaApi(app, providerId)
      }
    })

    test('shows validation error for invalid JMESPath and does not save', async ({ app }) => {
      const providerId = await createMappingTestProvider(app, 'e2e-jmespath-tab')
      try {
        await gotoGroupMappingEdit(app, providerId)

        await setGroupMappingExpression(app, INVALID_JMESPATH)
        await saveGroupMapping(app)

        await expect(app.getByText(/Invalid group extraction expression/i)).toBeVisible()
        await expect(app.getByRole('button', { name: /Save mapping/i })).toBeVisible()
        await expect(app.getByText('Group mapping saved')).not.toBeVisible()
      } finally {
        await deleteIdentityProviderViaApi(app, providerId)
      }
    })
  })

  test.describe('Add provider — Claim mapping step', () => {
    test('rejects invalid JMESPath when creating a provider', async ({ app }) => {
      const providerName = buildUniqueName('e2e-jmespath-claim-step')

      await gotoAddOidcProviderWizard(app)
      await fillMinimalOidcProviderFields(app, { name: providerName })
      await gotoClaimMappingWizardStep(app)

      await app.getByRole('textbox', { name: 'Group extraction expression', exact: true }).fill(INVALID_JMESPATH)
      await app.getByRole('button', { name: /Add provider/i }).click()

      await expect(app.getByText(/Invalid group extraction expression/i)).toBeVisible()
      await expect(app.getByRole('heading', { level: 1, name: 'Add OIDC provider' })).toBeVisible()
    })

    test('saves provider with valid JMESPath on claim mapping step', async ({ app }) => {
      const providerName = buildUniqueName('e2e-jmespath-claim-step')
      let createdProviderId: string | null = null

      try {
        await gotoAddOidcProviderWizard(app)
        await fillMinimalOidcProviderFields(app, { name: providerName })
        await gotoClaimMappingWizardStep(app)

        await app.getByRole('textbox', { name: 'Group extraction expression', exact: true }).fill(VALID_JMESPATH)
        await app.getByRole('button', { name: /Add provider/i }).click()

        await expect(app.getByText('Identity provider created')).toBeVisible()
        await expect(app.getByRole('row', { name: new RegExp(providerName) })).toBeVisible()

        const created = await findIdentityProviderByName(app, providerName)
        createdProviderId = created?.id ?? null
      } finally {
        if (createdProviderId) {
          await deleteIdentityProviderViaApi(app, createdProviderId)
        }
      }
    })
  })
})

test.describe('UI-14: Claim data configuration screen', () => {
  test('configures claim mappings and saves successfully', async ({ app }) => {
    const providerName = buildUniqueName('e2e-claim-mapping')
    let createdProviderId: string | null = null

    try {
      await gotoAddOidcProviderWizard(app)
      await fillMinimalOidcProviderFields(app, { name: providerName })
      await gotoClaimMappingWizardStep(app)

      await app.getByRole('textbox', { name: 'Email claim', exact: true }).fill('mail')

      await app.getByRole('button', { name: /Add provider/i }).click()

      await expect(app.getByText('Identity provider created')).toBeVisible()
      await expect(app.getByRole('row', { name: new RegExp(providerName) })).toBeVisible()

      const created = await findIdentityProviderByName(app, providerName)
      createdProviderId = created?.id ?? null
    } finally {
      if (createdProviderId) {
        await deleteIdentityProviderViaApi(app, createdProviderId)
      }
    }
  })
})
