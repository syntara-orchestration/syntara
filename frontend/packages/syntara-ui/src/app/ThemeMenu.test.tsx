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
      <ThemeMenu showTooltip={showTooltip} />
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

  it('has no accessibility violations when the menu is open', async () => {
    const user = userEvent.setup()
    renderThemeMenu()
    await user.click(screen.getByRole('button', { name: THEME_BUTTON }))
    // The menu portals to document.body, outside the masthead landmark, same as
    // other PatternFly poppers. The region rule flags that placement, not the controls.
    expect(await axe(document.body, { rules: { region: { enabled: false } } })).toHaveNoViolations()
  })

  it('closes with Escape and activates a contrast option with Enter', async () => {
    const user = userEvent.setup()
    renderThemeMenu()
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })

    await user.click(themeButton)
    expect(screen.getByRole('group', { name: 'Contrast mode' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Contrast mode' })).not.toBeInTheDocument()
    })

    await user.click(themeButton)
    await user.tab()
    expect(screen.getAllByRole('button', { name: 'System' })[0]).toHaveFocus()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Contrast mode' })).not.toBeInTheDocument()
    })

    await user.click(themeButton)
    const highContrast = screen.getByRole('button', { name: 'High contrast' })
    highContrast.focus()
    await user.keyboard('{Enter}')
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
    expect(highContrast).toHaveAttribute('aria-pressed', 'true')
  })

  it('stays open while tabbing between groups and closes when tab leaves the menu', async () => {
    const user = userEvent.setup()
    renderThemeMenu()
    const themeButton = screen.getByRole('button', { name: THEME_BUTTON })

    await user.click(themeButton)
    const glass = screen.getByRole('button', { name: 'Glass' })
    for (let step = 0; step < 7; step += 1) {
      await user.tab()
    }
    expect(glass).toHaveFocus()
    expect(screen.getByRole('group', { name: 'Color scheme' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Contrast mode' })).toBeInTheDocument()

    await user.tab()
    await waitFor(() => {
      expect(screen.queryByRole('group', { name: 'Contrast mode' })).not.toBeInTheDocument()
    })
  })
})
