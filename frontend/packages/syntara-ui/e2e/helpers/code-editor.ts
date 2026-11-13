import { type Page, expect } from '../fixtures'

export async function fillCodeEditor(
  page: Page,
  {
    value,
    label = 'Script code editor',
    inputMethod = 'type',
  }: { value: string; label?: string; inputMethod?: 'type' | 'insertText' }
) {
  const enterText = async () => {
    if (inputMethod === 'insertText') await page.keyboard.insertText(value)
    else await page.keyboard.type(value, { delay: 10 })
  }
  const typeInto = async (target: ReturnType<Page['locator']>) => {
    const textbox = target.getByRole('textbox', { name: label }).first()
    const monacoSurface = target.locator('.monaco-editor').first()

    // Wait for Monaco to finish async initialization — either the accessible
    // textbox or the .monaco-editor wrapper must be present before interacting.
    await expect(async () => {
      const hasTextbox = await textbox.isVisible()
      const hasMonaco = await monacoSurface.isVisible()
      if (!hasTextbox && !hasMonaco) throw new Error('Monaco editor not ready')
    }).toPass({ timeout: 15000, intervals: [500, 1000] })

    if (await textbox.isVisible()) {
      await textbox.click({ force: true })
      await page.keyboard.press('ControlOrMeta+A')
      await enterText()
      if (inputMethod === 'insertText' && (await monacoSurface.isVisible())) {
        // Monaco may use a contenteditable EditContext rather than a textarea.
        await expect(monacoSurface.locator('.view-lines')).toContainText(value)
      } else {
        await expect(textbox).toHaveValue(value)
      }
      return
    }

    await monacoSurface.click({ force: true })
    const usedMonacoApi = await page.evaluate((text) => {
      const w = window as unknown as Record<string, unknown>
      const editor = w.monaco
        ? (
            w.monaco as { editor: { getEditors: () => Array<{ setValue: (v: string) => void }> } }
          ).editor.getEditors()[0]
        : null
      if (editor) {
        editor.setValue(text)
        return true
      }
      const el = document.querySelector('.monaco-editor')
      if (el) {
        const textarea = el.querySelector('textarea')
        if (textarea) {
          textarea.focus()
          document.execCommand('selectAll')
          document.execCommand('insertText', false, text)
        }
      }
      return false
    }, value)
    if (!usedMonacoApi) {
      await expect(monacoSurface.locator('.view-lines')).toContainText(value.slice(0, 20))
    }
  }

  // Wait for at least one editor variant to appear
  await expect(async () => {
    const inlineCount = await page.getByTestId('inline-code-editor').locator(':visible').count()
    const modalCount = await page.getByTestId('modal-code-editor').locator(':visible').count()
    const roleCount = await page.getByRole('textbox', { name: label }).count()

    if (inlineCount === 0 && modalCount === 0 && roleCount === 0) {
      throw new Error('No code editor found')
    }
  }).toPass({ timeout: 15000, intervals: [500, 1000] })

  const visibleInlineEditor = page.getByTestId('inline-code-editor').locator(':visible').first()
  if ((await visibleInlineEditor.count()) > 0) {
    await typeInto(visibleInlineEditor)
    return
  }

  const visibleModalEditor = page.getByTestId('modal-code-editor').locator(':visible').first()
  if ((await visibleModalEditor.count()) > 0) {
    await typeInto(visibleModalEditor)
    return
  }

  const roleEditor = page.getByRole('textbox', { name: label }).first()
  await expect(roleEditor).toBeVisible()
  await roleEditor.click({ force: true })
  await page.keyboard.press('ControlOrMeta+A')
  await enterText()
  await expect(roleEditor).toHaveValue(value)
}
