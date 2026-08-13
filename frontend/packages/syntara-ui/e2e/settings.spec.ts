/**
 * E2E Tests: Settings Page
 *
 * Critical paths covered (UI-1 through UI-17 from Runtime Settings Test Plan):
 * - UI-1:  Page renders with category tabs
 * - UI-2:  Context Manager tab shows grouped section headings
 * - UI-3:  Navigate to settings via System Administration nav
 * - UI-4:  Auditor read-only view
 * - UI-5:  Viewer cannot access settings
 * - UI-6:  Modify integer setting, save, verify persistence
 * - UI-7:  Toggle boolean setting and save
 * - UI-8:  Modify float setting (0.1-step), save, reload, restore
 * - UI-9:  Modify string setting with allowed values dropdown
 * - UI-10: Modify JSON list setting (add/remove items)
 * - UI-11: (removed) Modify freeform string setting — no plain-text-input
 *   setting currently exists in the catalog; all remaining STRING settings
 *   use allowed_values and render as dropdowns (see UI-9).
 * - UI-12: Validation — out of range value shows inline error
 * - UI-13: Reset single setting via kebab menu
 * - UI-14: Reset all settings via confirmation modal
 * - UI-15: Reset to defaults confirmation modal cancel does not reset
 * - UI-16: Version conflict handling
 * - UI-17: Save includes optimistic locking version
 *
 * Edge cases:
 * - Settings persist after page reload
 * - Reset to defaults confirmation modal cancel does not reset
 * - Version conflict auto-refetches latest values
 */

import { createUnavailableGuard, expect, test, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { apiRequest } from './utils/api'

/** Navigate to settings and click the Context Manager tab. */
async function goToContextManager(app: import('@playwright/test').Page) {
  await app.goto(toAppUrl('/system-administration/settings'))
  const cmTab = app.getByRole('tab', { name: /Context Manager/i })
  await cmTab.click()
  await expect(app.locator('.pf-v6-c-form__section-title', { hasText: 'Compression' })).toBeVisible({ timeout: 5000 })
}

/** Navigate to settings and click the System tab. */
async function goToSystem(app: import('@playwright/test').Page) {
  await app.goto(toAppUrl('/system-administration/settings'))
  const sysTab = app.getByRole('tab', { name: 'System', exact: true })
  await sysTab.click()
  await expect(app.locator('[id="logging.log_level"]')).toBeVisible({ timeout: 5000 })
}

/** Reset a single setting via its kebab menu then save. */
async function resetSingleSetting(app: import('@playwright/test').Page, settingName: string) {
  const kebab = app.getByLabel(`Actions for ${settingName}`)
  await expect(kebab).toBeVisible({ timeout: 5000 })
  await kebab.click()
  await app.getByRole('menuitem', { name: 'Reset to default' }).click()
  const saveBtn = app.getByRole('button', { name: 'Save changes' })
  await expect(saveBtn).toBeEnabled()
  await saveBtn.click()
  await expect(saveBtn).toBeDisabled({ timeout: 5000 })
}

/** Reset all settings in the current tab to defaults via the confirmation modal, then save. */
async function resetAllToDefaults(app: import('@playwright/test').Page) {
  const resetBtn = app.getByRole('button', { name: 'Reset to defaults' })
  if (await resetBtn.isEnabled()) {
    await resetBtn.click()
    const resetAllBtn = app.getByRole('button', { name: 'Reset all' })
    if (await resetAllBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await resetAllBtn.click()
      // Save the reset values
      const saveBtn = app.getByRole('button', { name: 'Save changes' })
      if (await saveBtn.isEnabled({ timeout: 2000 }).catch(() => false)) {
        await saveBtn.click()
        await expect(saveBtn).toBeDisabled({ timeout: 5000 })
      }
    }
  }
}

test.describe('Settings', () => {
  // Settings tests share backend state — run serially to avoid conflicts.
  // mode: 'serial' is set by createUnavailableGuard below.
  const guard = createUnavailableGuard('Settings page has no tabs; backend may not have settings configured')

  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/system-administration/settings'))
    const heading = app.getByRole('heading', { level: 1, name: 'Settings' })
    const hasPage = await heading
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasPage) guard.markUnavailable()
    test.skip(!hasPage, 'Settings page not available; backend may not be running')
    const hasTabs = await app
      .getByRole('tab', { name: /Context Manager|System|Authentication/i })
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTabs) guard.markUnavailable()
    test.skip(!hasTabs, 'Settings page has no tabs; backend may not have settings configured')
  })

  test('page renders with category tabs', async ({ app }) => {
    await expect(app).toHaveTitle(`Settings | ${APP_TITLE}`)
    const tabCount = await app.getByRole('tab').count()
    expect(tabCount).toBeGreaterThanOrEqual(1)
  })

  test('context manager tab shows grouped section headings', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasCmTab, 'Context Manager tab not available')

    await cmTab.click()

    const groups = [
      'Compression',
      'Context assembly',
      'Grounding scores',
      'Performance',
      'Retrieval',
      'Snippets',
      'Token limits',
    ]
    for (const group of groups) {
      const title = app.locator('.pf-v6-c-form__section-title', { hasText: group })
      await title.scrollIntoViewIfNeeded()
      await expect(title).toBeVisible()
    }
  })

  test('save changes button is disabled when no edits', async ({ app }) => {
    const saveButton = app.getByRole('button', { name: 'Save changes' })
    await expect(saveButton).toBeVisible()
    await expect(saveButton).toBeDisabled()
  })

  test('modify integer setting, save, and verify persistence', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasCmTab, 'Context Manager tab not available')

    await cmTab.click()

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const input = formGroup.locator('input')
    const originalValue = await input.inputValue()

    try {
      // Click plus to increment
      await formGroup.getByRole('button', { name: /plus/i }).click()

      // Save
      const saveButton = app.getByRole('button', { name: 'Save changes' })
      await expect(saveButton).toBeEnabled()
      await saveButton.click()
      await expect(saveButton).toBeDisabled({ timeout: 5000 })

      // Reload and verify value persisted
      await app.goto(toAppUrl('/system-administration/settings'))
      await cmTab.click()
      const reloadedInput = app.locator('[id="context_manager.compression_loop"]').locator('..').locator('input')
      const newValue = await reloadedInput.inputValue()
      expect(Number(newValue)).toBe(Number(originalValue) + 1)
    } finally {
      // Cleanup: reset to defaults
      await goToContextManager(app)
      await resetAllToDefaults(app)
    }
  })

  test('toggle boolean setting and save', async ({ app }) => {
    const sysTab = app.getByRole('tab', { name: 'System', exact: true })
    const hasSysTab = await sysTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasSysTab, 'System tab not available')

    await sysTab.click()

    const formGroup = app.locator('[id="metrics.perf_test_mode"]').locator('..')
    const toggle = formGroup.getByRole('switch')
    const hasToggle = await toggle
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasToggle, 'Performance test mode toggle not found')

    // PF6 Switch renders a visual <span> overlay that intercepts pointer events
    const wasChecked = await toggle.isChecked()
    await toggle.click({ force: true })
    if (wasChecked) {
      await expect(toggle).not.toBeChecked()
    } else {
      await expect(toggle).toBeChecked()
    }

    const saveBtn = app.getByRole('button', { name: 'Save changes' })
    await expect(saveBtn).toBeEnabled()
    await saveBtn.click()
    await expect(saveBtn).toBeDisabled({ timeout: 5000 })
  })

  test('reset single setting via kebab menu', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasCmTab, 'Context Manager tab not available')

    await cmTab.click()

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    try {
      // Modify and save
      await formGroup.getByRole('button', { name: /plus/i }).click()
      await app.getByRole('button', { name: 'Save changes' }).click()
      await expect(app.getByRole('button', { name: 'Save changes' })).toBeDisabled({ timeout: 5000 })

      // Reload to get fresh state
      await goToContextManager(app)

      // Click the kebab menu and reset
      const kebab = app.getByLabel('Actions for Compression loop')
      await expect(kebab).toBeVisible({ timeout: 5000 })
      await kebab.click()
      await app.getByRole('menuitem', { name: 'Reset to default' }).click()

      // Save the reset value
      await expect(app.getByRole('button', { name: 'Save changes' })).toBeEnabled()
      await app.getByRole('button', { name: 'Save changes' }).click()
      await expect(app.getByRole('button', { name: 'Save changes' })).toBeDisabled({ timeout: 5000 })
    } finally {
      // Cleanup: ensure defaults
      await goToContextManager(app)
      await resetAllToDefaults(app)
    }
  })

  test('reset to defaults confirmation modal: cancel does not reset', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasCmTab, 'Context Manager tab not available')

    await cmTab.click()

    // Modify a setting to enable reset button
    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    await formGroup.getByRole('button', { name: /plus/i }).click()

    // Click Reset to defaults — modal should appear
    await app.getByRole('button', { name: 'Reset to defaults' }).click()
    await expect(app.getByText('This will reset all configuration values')).toBeVisible()

    // Click Cancel — modal should close, changes preserved
    await app.getByRole('button', { name: 'Cancel' }).click()
    await expect(app.getByText('This will reset all configuration values')).not.toBeVisible()
    await expect(app.getByRole('button', { name: 'Save changes' })).toBeEnabled()

    // No cleanup needed — changes were local only (not saved)
  })

  test('navigate to settings via System Administration nav', async ({ app }) => {
    // Navigate away first
    await app.goto(toAppUrl('/workflows'))
    await expect(app).toHaveURL(/workflows/)

    // Open System Administration flyout and click Settings
    await app.getByRole('button', { name: 'System Administration' }).click()
    await app.getByRole('menuitem', { name: 'Settings' }).click()

    // Verify navigation
    await expect(app).toHaveURL(/system-administration\/settings/)
    await expect(app.getByRole('tab', { name: /Context Manager/i })).toBeVisible()
  })

  test('auditor read-only view', async ({ auditorApp }) => {
    await auditorApp.goto(toAppUrl('/system-administration/settings'))
    const heading = auditorApp.getByRole('heading', { level: 1, name: 'Settings' })
    await expect(heading).toBeVisible({ timeout: 10_000 })

    // Wait for tabs to load (auditor has read access)
    const cmTab = auditorApp.getByRole('tab', { name: /Context Manager/i })
    const hasTabs = await cmTab
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTabs, 'Settings tabs not available for auditor')

    await cmTab.click()
    await expect(auditorApp.locator('.pf-v6-c-form__section-title', { hasText: 'Compression' })).toBeVisible({
      timeout: 5000,
    })

    // Save button should not be visible
    await expect(auditorApp.getByRole('button', { name: 'Save changes' })).not.toBeVisible()

    // Reset to defaults button should not be visible
    await expect(auditorApp.getByRole('button', { name: 'Reset to defaults' })).not.toBeVisible()

    // Kebab menus should not be visible
    await expect(auditorApp.getByLabel('Actions for Compression loop')).not.toBeVisible()

    // NumberInput should be disabled
    const intFormGroup = auditorApp.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(intFormGroup.locator('input')).toBeDisabled()

    // Switch should be disabled
    const sysTab = auditorApp.getByRole('tab', { name: 'System', exact: true })
    if (await sysTab.isVisible()) {
      await sysTab.click()
      const toggle = auditorApp.locator('[id="metrics.perf_test_mode"]').locator('..').getByRole('switch')
      if (await toggle.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(toggle).toBeDisabled()
      }
    }
  })

  test('viewer cannot access settings', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl('/system-administration/settings'))
    const heading = viewerApp.getByRole('heading', { level: 1, name: 'Settings' })
    await expect(heading).toBeVisible({ timeout: 10_000 })

    // Viewer should see access denied message
    await expect(viewerApp.getByText('Access denied')).toBeVisible({ timeout: 10_000 })

    // No category tabs should be visible
    const tabCount = await viewerApp.getByRole('tab').count()
    expect(tabCount).toBe(0)
  })

  test('modify float setting, save, and verify persistence', async ({ app }) => {
    await goToContextManager(app)

    const formGroup = app.locator('[id="context_manager.compression_temperature"]').locator('..')
    await formGroup.scrollIntoViewIfNeeded()
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const input = formGroup.locator('input')
    const originalValue = await input.inputValue()

    try {
      // Click plus to increment by 0.1
      await formGroup.getByRole('button', { name: /plus/i }).click()

      // Save
      const saveButton = app.getByRole('button', { name: 'Save changes' })
      await expect(saveButton).toBeEnabled()
      await saveButton.click()
      await expect(saveButton).toBeDisabled({ timeout: 5000 })

      // Reload and verify value persisted
      await goToContextManager(app)
      const reloadedInput = app.locator('[id="context_manager.compression_temperature"]').locator('..').locator('input')
      const newValue = await reloadedInput.inputValue()
      expect(Number(Number.parseFloat(newValue).toFixed(1))).toBe(
        Number((Number.parseFloat(originalValue) + 0.1).toFixed(1))
      )
    } finally {
      await goToContextManager(app)
      await resetSingleSetting(app, 'Compression temperature')
    }
  })

  test('modify string setting with allowed values dropdown', async ({ app }) => {
    await goToSystem(app)

    const formGroup = app.locator('[id="logging.log_level"]').locator('..')
    await formGroup.scrollIntoViewIfNeeded()
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const select = formGroup.locator('select')

    try {
      // Change to DEBUG
      await select.selectOption('DEBUG')

      // Save
      const saveButton = app.getByRole('button', { name: 'Save changes' })
      await expect(saveButton).toBeEnabled()
      await saveButton.click()
      await expect(saveButton).toBeDisabled({ timeout: 5000 })

      // Reload and verify persisted
      await goToSystem(app)
      const reloadedSelect = app.locator('[id="logging.log_level"]').locator('..').locator('select')
      await expect(reloadedSelect).toHaveValue('DEBUG')
    } finally {
      await goToSystem(app)
      await resetSingleSetting(app, 'System Log Level')
    }
  })

  test('modify JSON list setting', async ({ app }) => {
    await goToContextManager(app)

    // Scroll to Context assembly section
    const contextAssembly = app.locator('.pf-v6-c-form__section-title', { hasText: 'Context assembly' })
    await contextAssembly.scrollIntoViewIfNeeded()

    const formGroup = app.locator('[id="context_manager.priority_order"]').locator('..')
    await formGroup.scrollIntoViewIfNeeded()
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    try {
      // Remove the first item ("system") via its close button
      await formGroup.getByRole('button', { name: 'Close system' }).click()

      // Add a new item via the text input
      const input = formGroup.getByPlaceholder('Type a value and press Enter')
      await input.fill('test-item')
      await input.press('Enter')

      // Save
      const saveButton = app.getByRole('button', { name: 'Save changes' })
      await expect(saveButton).toBeEnabled()
      await saveButton.click()
      await expect(saveButton).toBeDisabled({ timeout: 5000 })

      // Reload and verify persisted
      await goToContextManager(app)
      const reloadedGroup = app.locator('[id="context_manager.priority_order"]').locator('..')
      await reloadedGroup.scrollIntoViewIfNeeded()
      await expect(reloadedGroup.getByText('test-item')).toBeVisible()
    } finally {
      await goToContextManager(app)
      const kebab = app.getByLabel('Actions for Priority order')
      await kebab.scrollIntoViewIfNeeded()
      await resetSingleSetting(app, 'Priority order')
    }
  })

  test('validation — out of range value shows inline error', async ({ app }) => {
    await goToContextManager(app)

    // Scroll to Grounding scores section
    const groundingSection = app.locator('.pf-v6-c-form__section-title', { hasText: 'Grounding scores' })
    await groundingSection.scrollIntoViewIfNeeded()

    const formGroup = app.locator('[id="context_manager.required_grounding_score"]').locator('..')
    await formGroup.scrollIntoViewIfNeeded()
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    // Set out-of-range value: triple-click to select all, then type the new value.
    // This triggers native keyboard events that React picks up correctly.
    const input = formGroup.locator('input')
    await input.click({ clickCount: 3 })
    await app.keyboard.type('1.5')

    // Assert inline error (search from page root — helper text is a sibling of the NumberInput container)
    await expect(app.getByText('Value must be at most 1')).toBeVisible()

    // Assert save button disabled
    await expect(app.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  test('reset all settings via confirmation modal', async ({ app }) => {
    await goToContextManager(app)

    // Modify a setting
    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const input = formGroup.locator('input')
    const originalValue = await input.inputValue()
    await formGroup.getByRole('button', { name: /plus/i }).click()

    // Click "Reset to defaults" — modal appears
    await app.getByRole('button', { name: 'Reset to defaults' }).click()
    await expect(app.getByText('This will reset all configuration values')).toBeVisible()

    // Click "Reset all"
    await app.getByRole('button', { name: 'Reset all' }).click()

    // Verify setting reverted to default
    await expect(input).toHaveValue(originalValue)

    // Save the reset
    const saveBtn = app.getByRole('button', { name: 'Save changes' })
    await expect(saveBtn).toBeEnabled()
    await saveBtn.click()
    await expect(saveBtn).toBeDisabled({ timeout: 5000 })
  })

  test('version conflict handling', async ({ app }) => {
    await goToContextManager(app)

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    try {
      // Increment in UI (don't save yet)
      await formGroup.getByRole('button', { name: /plus/i }).click()

      // Simulate concurrent edit: PATCH via API to bump the version
      const getResponse = await apiRequest(app, 'get', '/settings/context_manager.compression_loop')
      expect(getResponse.ok()).toBe(true)
      const setting = (await getResponse.json()) as { version: number; effective_value: unknown }

      const patchResponse = await apiRequest(app, 'patch', '/settings/context_manager.compression_loop', {
        data: {
          value: setting.effective_value,
          expected_version: setting.version,
        },
      })
      expect(patchResponse.ok()).toBe(true)

      // Now click Save in the UI — should trigger version conflict
      await app.getByRole('button', { name: 'Save changes' }).click()

      // Verify conflict alert
      await expect(app.getByText('Settings were modified by another user')).toBeVisible({ timeout: 5000 })

      // Save button should be disabled after auto-refetch
      await expect(app.getByRole('button', { name: 'Save changes' })).toBeDisabled({ timeout: 5000 })
    } finally {
      await goToContextManager(app)
      await resetAllToDefaults(app)
    }
  })

  test('save includes optimistic locking version', async ({ app }) => {
    await goToContextManager(app)

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    try {
      // Get current version via API
      const beforeResponse = await apiRequest(app, 'get', '/settings/context_manager.compression_loop')
      expect(beforeResponse.ok()).toBe(true)
      const beforeSetting = (await beforeResponse.json()) as { version: number }
      const versionBefore = beforeSetting.version

      // Increment and save via UI
      await formGroup.getByRole('button', { name: /plus/i }).click()
      const saveBtn = app.getByRole('button', { name: 'Save changes' })
      await expect(saveBtn).toBeEnabled()
      await saveBtn.click()
      await expect(saveBtn).toBeDisabled({ timeout: 5000 })

      // Query API again — version should be incremented
      const afterResponse = await apiRequest(app, 'get', '/settings/context_manager.compression_loop')
      expect(afterResponse.ok()).toBe(true)
      const afterSetting = (await afterResponse.json()) as { version: number }
      expect(afterSetting.version).toBe(versionBefore + 1)
    } finally {
      await goToContextManager(app)
      await resetAllToDefaults(app)
    }
  })

  test('modify local login for non-builtin users setting, save, and verify persistence', async ({ app }) => {
    const authTab = app.getByRole('tab', { name: /Authentication/i })
    const hasAuthTab = await authTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasAuthTab, 'Authentication tab not available')

    await authTab.click()

    const localLoginFormGroup = app.locator('[id="authentication.local_login_enabled"]').locator('..')
    const localLoginToggle = localLoginFormGroup.getByRole('switch')
    await expect(localLoginToggle).toBeVisible()
    await expect(localLoginToggle).toBeEnabled()
    const wasChecked = await localLoginToggle.isChecked()

    try {
      // Toggle switch to disable local login for non-builtin users
      // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
      await localLoginToggle.click({ force: true })
      if (wasChecked) {
        await expect(localLoginToggle).not.toBeChecked()
      } else {
        await expect(localLoginToggle).toBeChecked()
      }

      // Save
      const saveButton = app.getByRole('button', { name: 'Save changes' })
      await expect(saveButton).toBeEnabled()
      await saveButton.click()
      await expect(saveButton).toBeDisabled({ timeout: 5000 })

      // Reload and verify value persisted
      await app.goto(toAppUrl('/system-administration/settings'))
      await authTab.click()
      const reloadedToggle = app.locator('[id="authentication.local_login_enabled"]').locator('..').getByRole('switch')
      if (wasChecked) {
        await expect(reloadedToggle).not.toBeChecked()
      } else {
        await expect(reloadedToggle).toBeChecked()
      }
    } finally {
      // Cleanup: reset to defaults
      await app.goto(toAppUrl('/system-administration/settings'))
      await authTab.click()
      await resetAllToDefaults(app)
    }
  })
})
