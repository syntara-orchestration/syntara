import { type Locator, type Response } from '@playwright/test'

import { expect, type Page, toAppUrl } from '../fixtures'
import {
  apiRequest,
  createCredentialViaApi,
  deleteCredentialViaApi,
  ensureProject,
  listCredentialsByName,
} from '../utils/api'

import { buildUniqueName, selectFirstProject } from './workflows'

/**
 * Select a credential type from the PF6 Select dropdown.
 *
 * The credential type field uses a PF6 `Select` component (button toggle +
 * dropdown menu) instead of a native `<select>`. Interaction requires
 * clicking the toggle button to open the menu, then clicking the desired
 * option. The menu is portaled to the document body (PatternFly default),
 * so options are queried from the page rather than the modal container.
 */
export async function selectCredentialType(container: Locator, typeName: string): Promise<void> {
  const page = container.page()
  await container.getByRole('button', { name: 'Credential type', exact: true }).click()
  const option = page.getByRole('option', { name: typeName, exact: true })
  await option.waitFor({ state: 'visible', timeout: 10_000 })
  await option.click()
}

/** Open the Create Credential modal and return the dialog locator. */
export async function openCreateModal(app: Page) {
  await goToCredentialsList(app, { ensureCreateEnabled: true })
  await app.getByRole('button', { name: 'Create credential' }).first().click()
  const modal = app.getByRole('dialog')
  await expect(modal).toBeVisible()
  return modal
}

/** Navigate to the credentials list page and wait for it to load */
export async function goToCredentialsList(app: Page, options?: { ensureCreateEnabled?: boolean }) {
  if (options?.ensureCreateEnabled) {
    await ensureProject(app)
  }

  await app.goto(toAppUrl('/configuration/credentials'))
  await expect(app.getByText('Credentials', { exact: true }).first()).toBeVisible({ timeout: 20_000 })

  if (!options?.ensureCreateEnabled) return

  const createBtn = app.getByRole('button', { name: 'Create credential' }).first()
  await createBtn.waitFor({ state: 'visible', timeout: 10_000 })

  // Select a project so the Create Credential modal's Project field is pre-populated
  await selectFirstProject(app)
}

/**
 * Create a test credential — tries UI first, falls back to API.
 * Returns { name, id } for cleanup.
 */
export async function createTestCredential(
  app: Page,
  options: { prefix?: string; enabled?: boolean } = {}
): Promise<{ name: string; id: string | null }> {
  const name = buildUniqueName(options.prefix ?? 'e2e-cred')

  const project = await ensureProject(app)
  if (project) {
    const credId = await createCredentialViaApi(app, { name, projectId: project.id })
    if (credId) {
      if (options.enabled === false) {
        const resp = await apiRequest(app, 'patch', `/credentials/${credId}`, {
          data: { enabled: false },
        })
        if (!resp.ok()) {
          await disableCredential(app, name)
        }
      }
      return { name, id: credId }
    }
  }

  const uiCreated = await createTestCredentialViaUi(app, name)
  if (!uiCreated) {
    throw new Error(`Cannot create credential "${name}" via API or UI`)
  }

  if (options.enabled === false) {
    await disableCredential(app, name)
  }
  return { name, id: null }
}

async function createTestCredentialViaUi(app: Page, name: string): Promise<boolean> {
  try {
    await goToCredentialsList(app, { ensureCreateEnabled: true })
    await app.getByRole('button', { name: 'Create credential' }).first().click()

    const modal = app.getByRole('dialog')
    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'HTTP Bearer Token')
    await modal.getByRole('textbox', { name: 'Token' }).fill('e2e-test-token')
    await modal.getByRole('button', { name: 'Create credential' }).click()
    await expect(app.getByText('Credential created')).toBeVisible()
    return true
  } catch {
    return false
  }
}

async function disableCredential(app: Page, name: string): Promise<void> {
  await goToCredentialsList(app)
  await app.getByPlaceholder('Filter by keyword').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
  const row = app.getByRole('row', { name: new RegExp(name) })
  await row.getByRole('switch', { name: 'Enabled' }).click({ force: true })
  const dialog = app.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Disable' }).click()
  await expect(row.getByRole('switch')).not.toBeChecked()
}

/**
 * Delete a credential by name via the authenticated API (best-effort cleanup).
 */
export async function deleteCredentialByName(app: Page, name: string) {
  if (app.isClosed()) return
  try {
    const credentials = await listCredentialsByName(app, name)
    for (const cred of credentials) {
      await deleteCredentialViaApi(app, cred.id)
    }
  } catch {
    // Best-effort cleanup
  }
}

/**
 * Delete a credential by ID via the API (best-effort cleanup).
 */
export async function deleteCredentialById(app: Page, credentialId: string | null) {
  if (!credentialId || app.isClosed()) return
  await deleteCredentialViaApi(app, credentialId)
}

/**
 * Create a credential of any type via the UI.
 * Navigates to credentials list, opens create modal, fills fields, and submits.
 */
export async function createCredentialOfTypeViaUI(
  app: Page,
  options: {
    name: string
    type: string
    fields: Record<string, string>
  }
) {
  await goToCredentialsList(app, { ensureCreateEnabled: true })
  await app.getByRole('button', { name: 'Create credential' }).first().click()

  const modal = app.getByRole('dialog')
  await modal.getByRole('textbox', { name: 'Credential name' }).fill(options.name)
  await selectCredentialType(modal, options.type)

  for (const [fieldName, value] of Object.entries(options.fields)) {
    await modal.getByRole('textbox', { name: fieldName }).fill(value)
  }

  await modal.getByRole('button', { name: 'Create credential' }).click()
  await expect(app.getByText('Credential created')).toBeVisible()
}

/** Check if a response is a successful credentials API request (excludes credential_types). */
export const isCredentialsResponse = (resp: Response) =>
  resp.url().includes('/credentials') &&
  !resp.url().includes('/credential_types') &&
  resp.url().includes('for_action=use') &&
  resp.status() === 200

/** Filter the credentials list by keyword. */
export async function filterCredentialByName(app: Page, name: string) {
  await app.getByPlaceholder('Filter by keyword').fill(name)
  await app.getByRole('button', { name: 'Apply filter' }).click()
}

/**
 * Navigate to credentials list, filter by name, and click the credential name
 * link to open its detail page.
 */
export async function navigateToCredentialDetail(app: Page, credentialName: string) {
  await goToCredentialsList(app)

  await app.getByPlaceholder('Filter by keyword').fill(credentialName)
  await app.getByRole('button', { name: 'Apply filter' }).click()

  const table = app.getByRole('grid', { name: 'Credentials table' })
  await table.getByRole('link', { name: credentialName, exact: true }).click()
  await expect(app).toHaveURL(/configuration\/credentials\//)
  // Wait for the credential data to load — confirms the detail API responded
  await expect(app.locator('h1').filter({ hasText: credentialName })).toBeVisible({ timeout: 15_000 })
}
