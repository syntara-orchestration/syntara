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

import { createUnavailableGuard, type Page, expect, test, toAppUrl } from './fixtures'
import { APP_TITLE } from './helpers/appTitle'
import { apiRequest } from './utils/api'

/** Navigate to the Context Manager settings category. */
async function goToContextManager(app: Page) {
  await app.goto(toAppUrl('/system-administration/settings/context_manager'))
  // PF6 FormSection renders role="group" with the title as its accessible name.
  await expect(app.getByRole('group', { name: 'Compression' })).toBeVisible({ timeout: 10_000 })
}

/** Navigate to the System settings category. */
async function goToSystem(app: Page) {
  await app.goto(toAppUrl('/system-administration/settings/system'))
  // SynUrlTabs stubs empty tabpanels with aria-label={slug}; category fields render outside them.
  await expect(app.getByRole('tab', { name: 'System', exact: true })).toHaveAttribute('aria-selected', 'true', {
    timeout: 10_000,
  })
  await expect(app.getByRole('button', { name: 'System Log Level', exact: true })).toBeVisible({ timeout: 10_000 })
}

/** Navigate to the Authentication settings category. */
async function goToAuthentication(app: Page) {
  await app.goto(toAppUrl('/system-administration/settings/authentication'))
  await expect(app.getByRole('tab', { name: /Authentication/i })).toHaveAttribute('aria-selected', 'true', {
    timeout: 10_000,
  })
  await expect(app.getByRole('group', { name: 'Local login' })).toBeVisible({ timeout: 10_000 })
}

/** Reset a single setting via its kebab menu then save. No-op if already at default. */
async function resetSingleSetting(app: Page, settingName: string) {
  const kebab = app.getByLabel(`Actions for ${settingName}`)
  await expect(kebab).toBeVisible({ timeout: 5000 })
  await kebab.click()
  const resetItem = app.getByRole('menuitem', { name: 'Reset to default' })
  const isEnabled = await resetItem.isEnabled().catch(() => false)
  if (!isEnabled) {
    await app.keyboard.press('Escape')
    return
  }
  await resetItem.click()
  await saveSettingsChanges(app)
}

/** Save dirty settings and wait until the bulk PATCH succeeds. */
async function saveSettingsChanges(app: Page) {
  const saveButton = app.getByRole('button', { name: 'Save changes' })
  await expect(saveButton).toBeEnabled()
  const saved = app.waitForResponse(
    (res) => res.request().method() === 'PATCH' && res.url().includes('/settings') && res.ok()
  )
  await saveButton.click()
  await saved
  await expect(saveButton).toBeDisabled({ timeout: 5000 })
}

/** Reset all settings in the current tab to defaults via the confirmation modal, then save. */
async function resetAllToDefaults(app: Page) {
  const resetBtn = app.getByRole('button', { name: 'Reset to defaults' })
  if (await resetBtn.isEnabled()) {
    await resetBtn.click()
    const resetAllBtn = app.getByRole('button', { name: 'Reset all' })
    if (await resetAllBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await resetAllBtn.click()
      const saveBtn = app.getByRole('button', { name: 'Save changes' })
      if (await saveBtn.isEnabled({ timeout: 2000 }).catch(() => false)) {
        await saveSettingsChanges(app)
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
    expect(hasPage, 'Settings page not available; backend may not be running').toBeTruthy()
    // canRead is safe-false until POST /authz/can_i resolves, so the Access denied
    // empty state flashes while the Settings heading is already visible. Wait for tabs.
    const categoryTabs = app.getByRole('tab', { name: /Context Manager|Application|System|Authentication/i })
    const hasTabs = await expect(categoryTabs)
      .not.toHaveCount(0, { timeout: 30_000 })
      .then(() => true)
      .catch(() => false)
    if (!hasTabs) {
      const denied = await app.getByText(/don't have permission to view settings/i).isVisible()
      expect(denied, 'Admin was denied access to Settings').toBe(false)
      guard.markUnavailable()
    }
    expect(hasTabs, 'Settings page has no tabs; backend may not have settings configured').toBeTruthy()
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
    expect(hasCmTab, 'Context Manager tab not available').toBeTruthy()

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
      // PF6 FormSection renders role="group" with the title as its accessible name.
      const section = app.getByRole('group', { name: group })
      await section.scrollIntoViewIfNeeded()
      await expect(section).toBeVisible()
    }
  })

  test('save changes button is disabled when no edits', async ({ app }) => {
    const saveButton = app.getByRole('button', { name: 'Save changes' })
    await expect(saveButton).toBeVisible()
    await expect(saveButton).toBeDisabled()
  })

  test('modify integer setting, save, and verify persistence', async ({ app }) => {
    await goToContextManager(app)

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const input = formGroup.locator('input')
    const originalValue = await input.inputValue()

    try {
      // Click plus to increment
      await formGroup.getByRole('button', { name: /plus/i }).click()
      const expected = String(Number(originalValue) + 1)
      await expect(input).toHaveValue(expected)

      await saveSettingsChanges(app)

      // Reload via category deep-link so the field is on screen before we assert.
      await goToContextManager(app)
      const reloadedFormGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
      await expect(reloadedFormGroup).toBeVisible({ timeout: 5000 })
      const reloadedInput = reloadedFormGroup.locator('input')
      await expect(reloadedInput).toHaveValue(expected, { timeout: 10_000 })
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
    expect(hasSysTab, 'System tab not available').toBeTruthy()

    await sysTab.click()

    const formGroup = app.locator('[id="metrics.perf_test_mode"]').locator('..')
    const toggle = formGroup.getByRole('switch')
    const hasToggle = await toggle
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    expect(hasToggle, 'Performance test mode toggle not found').toBeTruthy()

    // PF6 Switch renders a visual <span> overlay that intercepts pointer events
    const wasChecked = await toggle.isChecked()
    await toggle.click({ force: true })
    if (wasChecked) {
      await expect(toggle).not.toBeChecked()
    } else {
      await expect(toggle).toBeChecked()
    }

    await saveSettingsChanges(app)
  })

  test('reset single setting via kebab menu', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    expect(hasCmTab, 'Context Manager tab not available').toBeTruthy()

    await cmTab.click()

    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })

    // Modify the value so it differs from the default
    await formGroup.getByRole('button', { name: /plus/i }).click()
    await expect(app.getByRole('button', { name: 'Save changes' })).toBeEnabled()

    // Click the kebab menu and reset to default
    const kebab = app.getByLabel('Actions for Compression loop')
    await expect(kebab).toBeVisible({ timeout: 5000 })
    await kebab.click()

    const resetItem = app.getByRole('menuitem', { name: 'Reset to default' })
    await expect(resetItem).toBeVisible({ timeout: 5000 })
    await resetItem.click()

    // Verify reset worked: re-open kebab — "Reset to default" should be disabled
    // (value now equals the default). This check is independent of server-saved state.
    await kebab.click()
    await expect(app.getByRole('menuitem', { name: 'Reset to default' })).toBeDisabled({ timeout: 5000 })
    await app.keyboard.press('Escape')
  })

  test('reset to defaults confirmation modal: cancel does not reset', async ({ app }) => {
    const cmTab = app.getByRole('tab', { name: /Context Manager/i })
    const hasCmTab = await cmTab
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    expect(hasCmTab, 'Context Manager tab not available').toBeTruthy()

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
    expect(hasTabs, 'Settings tabs not available for auditor').toBeTruthy()

    await cmTab.click()
    // PF6 FormSection renders role="group" with the title as its accessible name.
    await expect(auditorApp.getByRole('group', { name: 'Compression' })).toBeVisible({
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
      const expected = (Number.parseFloat(originalValue) + 0.1).toFixed(1)
      await expect(input).toHaveValue(expected)

      await saveSettingsChanges(app)

      // Reload and verify value persisted (toHaveValue retries while the form hydrates)
      await goToContextManager(app)
      const reloadedInput = app.locator('[id="context_manager.compression_temperature"]').locator('..').locator('input')
      await expect(reloadedInput).toHaveValue(expected, { timeout: 10_000 })
    } finally {
      await goToContextManager(app)
      await resetSingleSetting(app, 'Compression temperature')
    }
  })

  test('modify string setting with allowed values dropdown', async ({ app }) => {
    await goToSystem(app)

    const toggle = app.getByRole('button', { name: 'System Log Level', exact: true })
    await toggle.scrollIntoViewIfNeeded()
    await expect(toggle).toBeVisible({ timeout: 5000 })

    try {
      await toggle.click()
      const debugOption = app.getByRole('option', { name: 'DEBUG' })
      await expect(debugOption).toBeVisible()
      await debugOption.click()
      await expect(toggle).toContainText('DEBUG')

      await saveSettingsChanges(app)

      await goToSystem(app)
      await expect(app.getByRole('button', { name: 'System Log Level', exact: true })).toContainText('DEBUG', {
        timeout: 10_000,
      })
    } finally {
      await goToSystem(app)
      await resetSingleSetting(app, 'System Log Level')
    }
  })

  test('modify JSON list setting', async ({ app }) => {
    await goToContextManager(app)

    // Scroll to Context assembly section (PF6 FormSection renders role="group" with the title as its accessible name)
    const contextAssembly = app.getByRole('group', { name: 'Context assembly' })
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

      await saveSettingsChanges(app)

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

    // Scroll to Grounding scores section (PF6 FormSection renders role="group" with the title as its accessible name)
    const groundingSection = app.getByRole('group', { name: 'Grounding scores' })
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
    // Serial suite shares backend settings; start from catalog defaults so
    // originalValue is what "Reset all" restores (not a leftover increment).
    await resetAllToDefaults(app)
    await goToContextManager(app)

    // Modify a setting
    const formGroup = app.locator('[id="context_manager.compression_loop"]').locator('..')
    await expect(formGroup).toBeVisible({ timeout: 5000 })
    const input = formGroup.locator('input')
    const originalValue = await input.inputValue()
    await formGroup.getByRole('button', { name: /plus/i }).click()
    await expect(input).not.toHaveValue(originalValue)

    // Click "Reset to defaults" — modal appears
    await app.getByRole('button', { name: 'Reset to defaults' }).click()
    await expect(app.getByText('This will reset all configuration values')).toBeVisible()

    // Click "Reset all"
    await app.getByRole('button', { name: 'Reset all' }).click()

    // Verify setting reverted to default
    await expect(input).toHaveValue(originalValue)

    await saveSettingsChanges(app)
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
      await saveSettingsChanges(app)

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
    await goToAuthentication(app)

    const localLoginToggle = app.locator('[id="authentication.local_login_enabled"]').locator('..').getByRole('switch')
    await expect(localLoginToggle).toBeAttached({ timeout: 10_000 })
    await expect(localLoginToggle).toBeEnabled()
    const wasChecked = await localLoginToggle.isChecked()

    try {
      // PF6 Switch visually hides the <input role="switch"> — force bypasses the visibility check
      await localLoginToggle.click({ force: true })
      if (wasChecked) {
        await expect(localLoginToggle).not.toBeChecked()
      } else {
        await expect(localLoginToggle).toBeChecked()
      }

      await saveSettingsChanges(app)

      await goToAuthentication(app)
      const reloadedToggle = app.locator('[id="authentication.local_login_enabled"]').locator('..').getByRole('switch')
      await expect(reloadedToggle).toBeAttached({ timeout: 10_000 })
      if (wasChecked) {
        await expect(reloadedToggle).not.toBeChecked()
      } else {
        await expect(reloadedToggle).toBeChecked()
      }
    } finally {
      await goToAuthentication(app)
      await resetAllToDefaults(app)
    }
  })
})
