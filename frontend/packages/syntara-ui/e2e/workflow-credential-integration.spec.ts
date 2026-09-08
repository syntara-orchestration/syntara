import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { deleteCredentialByName, goToCredentialsList, selectCredentialType } from './helpers/credentials'
import { buildUniqueName, clickAddConnectedStep, selectProjectIfRequired } from './helpers/workflows'
import { ensureProject } from './utils/api'

/**
 * Navigate to the workflow builder and add an API action node form
 * where the credential selector is visible.
 *
 * Flow: New workflow → Manual trigger → Add connected step → Action → REST API
 */
async function navigateToApiActionForm(app: Page) {
  await ensureProject(app)
  await app.goto(toAppUrl('/workflow-builder/new'))
  await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

  await selectProjectIfRequired(app)

  await app.getByRole('button', { name: 'Manual trigger' }).click()
  await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Manual trigger')
  await app.getByRole('button', { name: 'Create' }).click()

  const credentialsLoaded = app.waitForResponse((resp) => resp.url().includes('/credentials') && resp.status() === 200)
  const panel = await clickAddConnectedStep(app)
  await panel.getByRole('button', { name: 'Action', exact: true }).click()
  await panel.getByRole('button', { name: 'REST API', exact: true }).click()

  await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
  await credentialsLoaded
  const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
  // The CredentialSelector re-queries when projectId populates (initial fetch without project_id,
  // then a second fetch with project_id). Use 30s to cover both fetches.
  await expect(credToggle).toBeEnabled({ timeout: 30_000 })
}

test.describe('Credential Selector', () => {
  test('credential selector appears in API action node form', async ({ app }) => {
    // Arrange & Act
    await navigateToApiActionForm(app)

    // Assert - Credential selector is visible
    await expect(app.getByRole('button', { name: 'Authentication credential', exact: true })).toBeVisible()
  })

  test('credential selector shows available credentials', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)

    // Act - Open the credential selector dropdown
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()

    // Assert - "Create new credential" option should always appear (allowCreate is true)
    await expect(app.getByRole('option', { name: /Create new credential/ })).toBeVisible()
  })

  test('select existing credential from selector', async ({ app }) => {
    const credName = buildUniqueName('e2e-select-cred')

    try {
      await goToCredentialsList(app, { ensureCreateEnabled: true })
      await app.getByRole('button', { name: 'Create credential' }).click()
      const createModal = app.getByRole('dialog')
      await createModal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      await selectCredentialType(createModal, 'HTTP Bearer Token')
      await createModal.getByRole('textbox', { name: 'Token' }).fill('select-test-token')
      await createModal.getByRole('button', { name: 'Create credential' }).click()
      await expect(app.getByText('Credential created')).toBeVisible()

      // Act - Navigate to API action form, open dropdown and select the credential
      await navigateToApiActionForm(app)
      const credToggle = app.getByRole('button', { name: 'Authentication credential', exact: true })
      await credToggle.click()

      // Wait for the option to appear (it may be further down in a grouped list)
      const option = app.getByRole('option', { name: credName, exact: true })
      await option.scrollIntoViewIfNeeded()
      await option.click()

      // Assert - Toggle now shows the selected credential name
      await expect(credToggle).toContainText(credName)
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })

  test('create new credential option appears in selector', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)

    // Act - Open the credential selector dropdown
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()

    // Assert - "Create new credential" option is visible
    await expect(app.getByRole('option', { name: /Create new credential/ })).toBeVisible()
  })

  test('credential selector filters by compatible type', async ({ app }) => {
    const incompatibleName = buildUniqueName('e2e-llm-incompat')

    try {
      await goToCredentialsList(app, { ensureCreateEnabled: true })
      await app.getByRole('button', { name: 'Create credential' }).click()
      const createModal = app.getByRole('dialog')
      await createModal.getByRole('textbox', { name: 'Credential name' }).fill(incompatibleName)
      await selectCredentialType(createModal, 'LLM Provider')
      await createModal.getByRole('textbox', { name: 'API Key' }).fill('test-llm-key')
      await createModal.getByRole('button', { name: 'Create credential' }).click()
      await expect(app.getByText('Credential created')).toBeVisible()

      // Act - Navigate to API action form (only shows HTTP Bearer Token and HTTP Basic Auth)
      await navigateToApiActionForm(app)
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()

      // Assert - Incompatible LLM credential is NOT in the list
      await expect(app.getByRole('option', { name: incompatibleName, exact: true })).not.toBeVisible()
    } finally {
      await deleteCredentialByName(app, incompatibleName)
    }
  })

  // Skip: CredentialSelector has no "No credential" option to clear selection
  test.skip('clear credential selection', async ({ app }) => {
    // Arrange - Create a credential and select it
    const credName = buildUniqueName('e2e-clear-cred')

    try {
      await goToCredentialsList(app, { ensureCreateEnabled: true })
      await app.getByRole('button', { name: 'Create credential' }).click()
      const createModal = app.getByRole('dialog')
      await createModal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      await selectCredentialType(createModal, 'HTTP Bearer Token')
      await createModal.getByRole('textbox', { name: 'Token' }).fill('clear-test-token')
      await createModal.getByRole('button', { name: 'Create credential' }).click()
      await expect(app.getByText('Credential created')).toBeVisible()

      await navigateToApiActionForm(app)
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
      await app.getByRole('option', { name: credName, exact: true }).click()
      await expect(app.getByRole('button', { name: 'Authentication credential', exact: true })).toContainText(credName)

      // Act - Open dropdown and click "No credential" to clear
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
      await app.getByRole('option', { name: /No credential/ }).click()

      // Assert - Toggle returns to default text
      await expect(app.getByRole('button', { name: 'Authentication credential', exact: true })).toContainText(
        'No credential'
      )
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})

test.describe('Inline Credential Creation', () => {
  test('open inline credential creation modal', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)

    // Act - Open dropdown and click "Create new credential"
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
    await app.getByRole('option', { name: /Create new credential/ }).click()

    // Assert - Modal opens with title
    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()
    await expect(modal.getByRole('heading', { name: 'Create credential' })).toBeVisible()
  })

  test('inline modal allows credential type selection when multiple types are compatible', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
    await app.getByRole('option', { name: /Create new credential/ }).click()

    // Assert - REST API has two compatible types (HTTP Bearer Token, HTTP Basic Auth),
    // so the credential type dropdown remains enabled for selection
    const modal = app.getByRole('dialog')
    await expect(modal.getByRole('button', { name: 'Credential type', exact: true })).toBeEnabled()
  })

  test.skip('create credential inline and auto-select', async ({ app }) => {
    const credName = buildUniqueName('e2e-inline-cred')

    try {
      // Arrange
      await navigateToApiActionForm(app)
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
      await app.getByRole('option', { name: /Create new credential/ }).click()

      // Act - Fill and submit the inline creation form
      const modal = app.getByRole('dialog')
      await modal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      // The pre-selected type is HTTP Bearer Token (first compatible type for API action)
      await expect(modal.getByRole('textbox', { name: 'Token' })).toBeVisible()
      await modal.getByRole('textbox', { name: 'Token' }).fill('inline-test-token')

      // Wait for both the POST (create) and the GET (refetch) to complete
      const credentialsRefetched = app.waitForResponse(
        (resp) => resp.url().includes('/credentials') && resp.request().method() === 'GET' && resp.status() === 200
      )
      await modal.getByRole('button', { name: 'Create credential' }).click()

      // Assert - Success and auto-selected (wait for refetch so the toggle label updates)
      await expect(app.getByText('Credential created')).toBeVisible()
      await credentialsRefetched
      await expect(app.getByRole('button', { name: 'Authentication credential', exact: true })).toContainText(credName)
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })

  test('cancel inline creation closes modal', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
    await app.getByRole('option', { name: /Create new credential/ }).click()

    // Act - Click Cancel
    const modal = app.getByRole('dialog')
    await expect(modal).toBeVisible()
    await modal.getByRole('button', { name: 'Cancel' }).click()

    // Assert - Modal closed, no credential selected (shows placeholder text)
    await expect(modal).not.toBeVisible()
    await expect(app.getByRole('button', { name: 'Authentication credential', exact: true })).toContainText(
      'Select credential'
    )
  })

  test('inline creation validates required fields', async ({ app }) => {
    // Arrange
    await navigateToApiActionForm(app)
    await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
    await app.getByRole('option', { name: /Create new credential/ }).click()

    // Act - Submit without filling required fields
    const modal = app.getByRole('dialog')
    await modal.getByRole('button', { name: 'Create credential' }).click()

    // Assert - Validation errors shown
    // Scope to the Name field's FormGroup to avoid matching "Username is required"
    await expect(
      modal
        .getByRole('textbox', { name: 'Credential name' })
        .locator('xpath=ancestor::div[contains(@class,"form__group")]')
        .getByText('Name is required')
    ).toBeVisible()
  })

  test('newly created credential is available in selector', async ({ app }) => {
    const credName = buildUniqueName('e2e-available-cred')

    try {
      // Arrange - Create a credential via inline modal
      await navigateToApiActionForm(app)
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()
      await app.getByRole('option', { name: /Create new credential/ }).click()

      const modal = app.getByRole('dialog')
      await modal.getByRole('textbox', { name: 'Credential name' }).fill(credName)
      await modal.getByRole('textbox', { name: 'Token' }).fill('availability-test-token')

      // Wait for the GET (refetch) after creation so the dropdown has fresh data
      const credentialsRefetched = app.waitForResponse(
        (resp) => resp.url().includes('/credentials') && resp.request().method() === 'GET' && resp.status() === 200
      )
      await modal.getByRole('button', { name: 'Create credential' }).click()
      await expect(app.getByText('Credential created')).toBeVisible()
      await credentialsRefetched

      // Act - Open the selector dropdown again
      await app.getByRole('button', { name: 'Authentication credential', exact: true }).click()

      // Assert - Newly created credential appears in the list
      const option = app.getByRole('option', { name: credName, exact: true })
      await option.scrollIntoViewIfNeeded()
      await expect(option).toBeVisible()
    } finally {
      await deleteCredentialByName(app, credName)
    }
  })
})
