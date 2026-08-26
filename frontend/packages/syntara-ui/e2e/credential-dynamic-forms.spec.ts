import { generateKeyPairSync } from 'node:crypto'

import { type Page } from './fixtures'
import { test, expect } from './fixtures'
import { deleteCredentialByName, goToCredentialsList, selectCredentialType } from './helpers/credentials'
import { buildUniqueName } from './helpers/workflows'

function generateTestSSHKey(): string {
  const { privateKey } = generateKeyPairSync('ed25519', {
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
    publicKeyEncoding: { type: 'spki', format: 'pem' },
  })
  return privateKey
}

async function openCreateModal(app: Page) {
  await goToCredentialsList(app, { ensureCreateEnabled: true })
  await app.getByRole('button', { name: 'Create credential' }).click()
  const modal = app.getByRole('dialog')
  await expect(modal).toBeVisible()
  return modal
}

test.describe('Dynamic Credential Form Rendering', () => {
  // --- HTTP Bearer Token (1 field: token) ---

  test('HTTP Bearer Token: form renders correct fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'HTTP Bearer Token')

    await expect(modal.getByRole('textbox', { name: 'Token' })).toBeVisible()
    await expect(modal.getByRole('button', { name: /Show secret|Hide secret/ })).toBeVisible()
  })

  test('HTTP Bearer Token: create credential succeeds', async ({ app }) => {
    const modal = await openCreateModal(app)
    const name = buildUniqueName('e2e-bearer')

    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'HTTP Bearer Token')
    await modal.getByRole('textbox', { name: 'Token' }).fill('test-bearer-token-value')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    try {
      await expect(app.getByText('Credential created')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('HTTP Bearer Token: validation shows errors for required fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'HTTP Bearer Token')

    // Fill name so Zod validation passes and dynamic field validation runs
    await modal.getByRole('textbox', { name: 'Credential name' }).fill('validation-test')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    await expect(modal.getByText('Token is required')).toBeVisible()
  })

  // --- HTTP Basic Auth (2 fields: username, password) ---

  test('HTTP Basic Auth: form renders correct fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'HTTP Basic Auth')

    await expect(modal.getByRole('textbox', { name: 'Username' })).toBeVisible()
    await expect(modal.getByRole('textbox', { name: 'Password' })).toBeVisible()
  })

  test('HTTP Basic Auth: create credential succeeds', async ({ app }) => {
    const modal = await openCreateModal(app)
    const name = buildUniqueName('e2e-basic')

    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'HTTP Basic Auth')
    await modal.getByRole('textbox', { name: 'Username' }).fill('testuser')
    await modal.getByRole('textbox', { name: 'Password' }).fill('testpass123')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    try {
      await expect(app.getByText('Credential created')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('HTTP Basic Auth: validation shows errors for required fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'HTTP Basic Auth')

    // Fill name so Zod validation passes and dynamic field validation runs
    await modal.getByRole('textbox', { name: 'Credential name' }).fill('validation-test')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    await expect(modal.getByText('Username is required')).toBeVisible()
    await expect(modal.getByText('Password is required')).toBeVisible()
  })

  // --- SSH Key (2 fields: username, ssh_private_key as multiline textarea) ---

  test('SSH Key: form renders correct fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'SSH Key')

    await expect(modal.getByRole('textbox', { name: 'Username' })).toBeVisible()
    await expect(modal.getByRole('textbox', { name: 'Private key' })).toBeVisible()
  })

  test('SSH Key: create credential succeeds', async ({ app }) => {
    const modal = await openCreateModal(app)
    const name = buildUniqueName('e2e-ssh')

    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'SSH Key')
    await modal.getByRole('textbox', { name: 'Username' }).fill('deploy')
    await modal.getByRole('textbox', { name: 'Private key' }).fill(generateTestSSHKey())
    await modal.getByRole('button', { name: 'Create credential' }).click()

    try {
      await expect(app.getByText('Credential created')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('SSH Key: validation shows errors for required fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'SSH Key')

    // Fill name so Zod validation passes and dynamic field validation runs
    await modal.getByRole('textbox', { name: 'Credential name' }).fill('validation-test')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    await expect(modal.getByText('Username is required')).toBeVisible()
    await expect(modal.getByText('Private key is required')).toBeVisible()
  })

  // --- LLM Provider (requires API key only) ---

  test('LLM Provider: form renders correct fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'LLM Provider')

    await expect(modal.getByRole('textbox', { name: 'API Key' })).toBeVisible()
  })

  test('LLM Provider: create credential succeeds', async ({ app }) => {
    const modal = await openCreateModal(app)
    const name = buildUniqueName('e2e-llm')

    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'LLM Provider')
    await modal.getByRole('textbox', { name: 'API Key' }).fill('sk-ant-test-key-123')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    try {
      await expect(app.getByText('Credential created')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })

  test('LLM Provider: validation shows errors for required fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'LLM Provider')

    // Fill name so Zod validation passes and dynamic field validation runs
    await modal.getByRole('textbox', { name: 'Credential name' }).fill('validation-test')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    await expect(modal.getByText('API Key is required')).toBeVisible()
  })

  // --- Ansible Automation Platform (mutually exclusive: OAuth2 Token vs Username+Password) ---

  test('Ansible Automation Platform: form renders correct fields', async ({ app }) => {
    const modal = await openCreateModal(app)
    await selectCredentialType(modal, 'Ansible Automation Platform')

    // Scope to the form to avoid matching the dialog's own aria-label
    const form = modal.locator('form')

    // Auth method selector is visible with OAuth2 Token selected by default
    await expect(form.getByLabel('Auth method', { exact: true })).toBeVisible()
    await expect(form.getByRole('textbox', { name: 'OAuth Token' })).toBeVisible()
    await expect(form.getByRole('textbox', { name: 'Username' })).not.toBeVisible()
    await expect(form.getByRole('textbox', { name: 'Password' })).not.toBeVisible()

    // Switch to Basic Auth — Username + Password appear, OAuth Token hides
    await form.getByLabel('Auth method', { exact: true }).click()
    await modal.getByRole('option', { name: 'Basic Auth' }).click()
    await expect(form.getByRole('textbox', { name: 'Username' })).toBeVisible()
    await expect(form.getByRole('textbox', { name: 'Password' })).toBeVisible()
    await expect(form.getByRole('textbox', { name: 'OAuth Token' })).not.toBeVisible()
  })

  test('Ansible Automation Platform: create credential succeeds', async ({ app }) => {
    const modal = await openCreateModal(app)
    const name = buildUniqueName('e2e-aap')

    await modal.getByRole('textbox', { name: 'Credential name' }).fill(name)
    await selectCredentialType(modal, 'Ansible Automation Platform')
    await modal.getByRole('textbox', { name: 'OAuth Token' }).fill('test-oauth-token')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    try {
      await expect(app.getByText('Credential created')).toBeVisible()
    } finally {
      await deleteCredentialByName(app, name)
    }
  })
})
