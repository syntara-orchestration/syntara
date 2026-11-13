import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { COLOR_SCHEME_STORAGE_KEY } from '../providers/theme/colorScheme'
import { ColorSchemeProvider } from '../providers/theme/ColorSchemeProvider'
import { CONTRAST_MODE_STORAGE_KEY } from '../providers/theme/contrastMode'

import { ThemeMenu } from './ThemeMenu'

const THEME_BUTTON = 'Theme, color scheme System, contrast System'

function renderThemeMenu(showTooltip = false) {
  return render(
    <ColorSchemeProvider>
      <button type="button">Before theme</button>
      <ThemeMenu showTooltip={showTooltip} />
      <button type="button">After theme</button>
    </ColorSchemeProvider>
  )
}

describe('ThemeMenu', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.add('pf-v6-theme-dark', 'pf-v6-theme-glass')
    document.documentElement.classList.remove('pf-v6-theme-high-contrast')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass', 'pf-v6-theme-high-contrast')
  })

  it('has no accessibility violations when closed', async () => {
    const { container } = renderThemeMenu()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('opens color scheme and contrast controls that stay independent', async () => {
    const user = userEvent.setup()
    renderThemeMenu()

    await user.click(screen.getByRole('button', { name: THEME_BUTTON }))
    expect(screen.getByRole('group', { name: 'Color scheme' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Contrast mode' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'System' })).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: 'High contrast' }))
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true)
    expect(localStorage.getItem(CONTRAST_MODE_STORAGE_KEY)).toBe('high-contrast')
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('light')
    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'High contrast' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: 'Glass' }))
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(true)
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Default' }))
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(false)
    expect(localStorage.getItem(CONTRAST_MODE_STORAGE_KEY)).toBe('default')
  })

  it('has no accessibility violations when the disclosure is open', async () => {
    const user = userEvent.setup()
    const { container } = renderThemeMenu()
    await user.click(screen.getByRole('button', { name: THEME_BUTTON }))
    expect(await axe(container)).toHaveNoViolations()
  })

  it.each([
    ['Enter', '{Enter}'],
    ['Space', ' '],
  ])('expands the theme disclosure with %s and tabs into its options', async (_key, activationKey) => {
    const user = userEvent.setup()
    renderThemeMenu()
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })

    await user.tab()
    await user.tab()
    expect(themeButton).toHaveFocus()
    await user.keyboard(activationKey)
    expect(themeButton).toHaveAttribute('aria-expanded', 'true')
    expect(themeButton).toHaveFocus()

    await user.tab()
    const firstSystem = screen.getAllByRole('button', { name: 'System' })[0]
    expect(firstSystem).toHaveFocus()
    expect(screen.getByRole('group', { name: 'Contrast mode' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Theme settings' })).not.toBeInTheDocument()
    })
    expect(themeButton).toHaveAttribute('aria-expanded', 'false')
    expect(themeButton).toHaveFocus()

    await user.click(themeButton)
    const highContrast = screen.getByRole('button', { name: 'High contrast' })
    highContrast.focus()
    await user.keyboard('{Enter}')
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
    expect(highContrast).toHaveAttribute('aria-pressed', 'true')
  })

  it('hides the dock tooltip while the disclosure is open', async () => {
    const user = userEvent.setup()
    renderThemeMenu(true)
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })

    await user.click(themeButton)
    expect(screen.getByRole('group', { name: 'Color scheme' })).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('lets Tab leave the disclosure and return to it in both directions', async () => {
    const user = userEvent.setup()
    renderThemeMenu()
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })
    const beforeTheme = screen.getByRole('button', { name: 'Before theme' })
    const afterTheme = screen.getByRole('button', { name: 'After theme' })

    await user.click(themeButton)
    const firstSystem = screen.getAllByRole('button', { name: 'System' })[0]
    const glass = screen.getByRole('button', { name: 'Glass' })
    expect(themeButton).toHaveFocus()

    await user.tab()
    expect(firstSystem).toHaveFocus()
    for (let step = 0; step < 4; step += 1) {
      await user.tab()
    }
    expect(screen.getByRole('button', { name: 'Default' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'High contrast' })).toHaveFocus()
    await user.tab()
    expect(glass).toHaveFocus()

    await user.tab()
    expect(afterTheme).toHaveFocus()
    expect(screen.getByRole('group', { name: 'Theme settings' })).toBeInTheDocument()

    await user.tab({ shift: true })
    expect(glass).toHaveFocus()
    for (let step = 0; step < 6; step += 1) {
      await user.tab({ shift: true })
    }
    expect(firstSystem).toHaveFocus()
    await user.tab({ shift: true })
    expect(themeButton).toHaveFocus()
    await user.tab({ shift: true })
    expect(beforeTheme).toHaveFocus()
    expect(screen.getByRole('group', { name: 'Theme settings' })).toBeInTheDocument()

    await user.click(themeButton)
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Theme settings' })).not.toBeInTheDocument()
    })
    expect(themeButton).toHaveFocus()
  })

  it('keeps the disclosure open after selecting an option, then closes on outside click', async () => {
    const user = userEvent.setup()
    renderThemeMenu()
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })

    await user.click(themeButton)
    const light = screen.getByRole('button', { name: 'Light' })
    await user.click(light)
    expect(light).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('group', { name: 'Theme settings' })).toBeInTheDocument()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'After theme' }))
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Theme settings' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'After theme' })).toHaveFocus()
  })
})
