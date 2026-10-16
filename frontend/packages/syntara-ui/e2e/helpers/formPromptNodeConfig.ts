/**
 * Workflow builder helpers for form_prompt (form step) node configuration.
 * Field-level builder helpers live in formFieldBuilder.ts.
 */
import { expect, type Page } from '../fixtures'

import { scrollFormFieldBuilderIntoView, setFormFieldLabel } from './formFieldBuilder'
import { addScriptOnHandle, openFormPromptCreateForm } from './v2-nodes'
import { closeNodeEditorPanel, triggerLayout } from './workflows'

export const FORM_PROMPT_NODE_FORM_TEST_ID = 'form-prompt-node-form'

export function formPromptNodeFormScope(page: Page) {
  return page.getByTestId(FORM_PROMPT_NODE_FORM_TEST_ID)
}

export async function openFormPromptNodeFormFromCatalog(page: Page) {
  await openFormPromptCreateForm(page)
}

export function formPromptCanvasNode(page: Page, nodeName: string) {
  return page
    .locator('[role="group"][aria-roledescription="node"].react-flow__node-form_prompt')
    .filter({ has: page.getByText(nodeName, { exact: true }) })
}

export async function expectFormPromptNodeOnCanvas(page: Page, nodeName: string) {
  const node = formPromptCanvasNode(page, nodeName)
  await expect(node).toBeVisible({ timeout: 15_000 })
  await expect(node.getByText('Form', { exact: true })).toBeVisible()
  await expect(node.getByText('Submitted', { exact: true })).toBeVisible()
  await expect(node.getByText('Fallback', { exact: true })).toBeVisible()
}

export async function fillFormSubmissionWindow(page: Page, totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  await page.getByLabel('Hours').fill(String(hours))
  await page.getByLabel('Minutes').fill(String(minutes))
  await page.getByLabel('Seconds').fill(String(seconds))
}

export async function setFormPromptEngineDurationSeconds(page: Page, seconds: number) {
  await page.getByRole('tab', { name: 'Settings' }).click()
  const durationInput = page.getByRole('spinbutton', { name: 'Expected duration (seconds)' })
  await expect(durationInput).toBeVisible({ timeout: 10_000 })
  await durationInput.fill(String(seconds))
  await page.getByRole('tab', { name: 'Parameters' }).click()
}

export async function enableFormPromptContinueOnFailure(page: Page) {
  const enableLink = page.getByRole('button', { name: 'Enable continue on failure' })
  if (await enableLink.isVisible().catch(() => false)) {
    await enableLink.click()
  }
  await expect(page.getByText('Fallback decision')).toBeVisible({ timeout: 10_000 })
}

export async function setFormPromptFallbackDecision(page: Page, decision: 'fallback' | 'submit') {
  await enableFormPromptContinueOnFailure(page)
  const fallbackToggle = page.getByRole('button', { name: 'Fallback decision', exact: true })
  await expect(fallbackToggle).toBeEnabled({ timeout: 10_000 })
  await fallbackToggle.click()
  const optionName = decision === 'submit' ? 'Submitted path' : 'Fallback path (default)'
  const visibleOption = page.getByRole('option', { name: optionName }).filter({ visible: true })
  await expect(visibleOption).toHaveCount(1, { timeout: 10_000 })
  await visibleOption.click()
}

export async function selectResponderUserFromPicker(page: Page, username: string) {
  const responderUsersButton = page.getByPlaceholder(/Select users/i)
  await expect(responderUsersButton).toBeVisible({ timeout: 15_000 })
  await responderUsersButton.click()

  await expect(page.getByRole('listbox')).toBeVisible({ timeout: 5_000 })
  const responderMenuItem = page.getByRole('menuitem').filter({ hasText: username })

  await expect(async () => {
    const count = await responderMenuItem.count()
    if (count === 0) {
      const menuItems = page.getByRole('menuitem')
      const menuItemCount = await menuItems.count()
      if (menuItemCount === 0) {
        throw new Error('No responder user menu items rendered yet')
      }
      const texts = await Promise.all((await menuItems.all()).map((item) => item.textContent()))
      throw new Error(`${username} not found. Available: ${texts.join(', ')}`)
    }
  }).toPass({ timeout: 15_000 })

  await responderMenuItem.first().click()
  await page.keyboard.press('Escape')
}

export async function enterResponderUserManually(page: Page, username: string) {
  const responderInput = page
    .getByPlaceholder(/Select a project to load responder users/i)
    .or(page.getByPlaceholder(/Type a username and press Enter/i))
    .or(page.getByPlaceholder(/Select users/i))
  await expect(responderInput).toBeVisible({ timeout: 10_000 })
  await responderInput.click()
  await responderInput.fill(username)
  await page.keyboard.press('Enter')
  await expect(formPromptNodeFormScope(page).getByText(username, { exact: true })).toBeVisible({ timeout: 10_000 })
}

export async function selectResponderGroupFromPicker(page: Page, groupName: string) {
  const groupsButton = page.getByPlaceholder(/Select groups/i)
  await expect(groupsButton).toBeVisible({ timeout: 15_000 })
  await groupsButton.click()

  const groupsListbox = page
    .getByRole('listbox')
    .filter({ has: page.getByRole('menuitem', { name: groupName, exact: true }) })
  await expect(groupsListbox).toBeVisible({ timeout: 5_000 })
  await groupsListbox.getByRole('menuitem', { name: groupName, exact: true }).click()
  await page.keyboard.press('Escape')
  await expect(formPromptNodeFormScope(page).getByText(groupName, { exact: true })).toBeVisible({
    timeout: 10_000,
  })
}

export async function configureOpenFormPromptNode(
  page: Page,
  config: {
    name: string
    message?: string
    responseWindowSeconds?: number
    engineDurationSeconds?: number
    fallbackDecision?: 'fallback' | 'submit'
    responderUserPicker?: string
    responderUserManual?: string
    responderGroup?: string
    formFieldLabel?: string
  }
) {
  const nameInput = page.getByRole('textbox', { name: 'Name', exact: true })
  await nameInput.fill(config.name)

  if (config.responderUserPicker) {
    await selectResponderUserFromPicker(page, config.responderUserPicker)
  }
  if (config.responderUserManual) {
    await enterResponderUserManually(page, config.responderUserManual)
  }
  if (config.responderGroup) {
    await selectResponderGroupFromPicker(page, config.responderGroup)
  }

  if (config.message) {
    await page.getByRole('textbox', { name: 'Message', exact: true }).fill(config.message)
  }

  if (config.formFieldLabel) {
    await scrollFormFieldBuilderIntoView(page)
    await expect(page.getByRole('heading', { name: 'Form fields' })).toBeVisible()
    await setFormFieldLabel(page, 1, config.formFieldLabel)
  }

  if (config.responseWindowSeconds !== undefined) {
    await fillFormSubmissionWindow(page, config.responseWindowSeconds)
  }

  if (config.engineDurationSeconds !== undefined) {
    await setFormPromptEngineDurationSeconds(page, config.engineDurationSeconds)
  }

  if (config.fallbackDecision) {
    await setFormPromptFallbackDecision(page, config.fallbackDecision)
  }
}

export async function createFormPromptNodeFromOpenForm(page: Page) {
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Create', exact: true })).not.toBeAttached({ timeout: 15_000 })
  await closeNodeEditorPanel(page)
}

export async function wireFormPromptSubmittedBranch(page: Page, nodeName: string, scriptTitle?: string) {
  await triggerLayout(page)
  await addScriptOnHandle(page, 'submitted', scriptTitle ?? `${nodeName} submitted path`, 'print("submitted")')
}
