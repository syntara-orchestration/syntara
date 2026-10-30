import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { COLOR_SCHEME_STORAGE_KEY } from './colorScheme'
import { ColorSchemeProvider } from './ColorSchemeProvider'
import { CONTRAST_MODE_STORAGE_KEY } from './contrastMode'
import { useColorScheme } from './useColorScheme'

function SchemeProbe() {
  const {
    colorScheme,
    colorSchemePreference,
    setColorScheme,
    toggleColorScheme,
    contrastMode,
    contrastPreference,
    setContrastMode,
  } = useColorScheme()
  return (
    <div>
      <p>Scheme: {colorScheme}</p>
      <p>Scheme preference: {colorSchemePreference}</p>
      <p>Contrast: {contrastMode}</p>
      <p>Contrast preference: {contrastPreference}</p>
      <button type="button" onClick={() => setColorScheme('light')}>
        Set light
      </button>
      <button type="button" onClick={() => setColorScheme('dark')}>
        Set dark
      </button>
      <button type="button" onClick={() => setColorScheme('system')}>
        Set system scheme
      </button>
      <button type="button" onClick={toggleColorScheme}>
        Toggle
      </button>
      <button type="button" onClick={() => setContrastMode('high-contrast')}>
        Set high contrast
      </button>
      <button type="button" onClick={() => setContrastMode('default')}>
        Set default contrast
      </button>
      <button type="button" onClick={() => setContrastMode('glass')}>
        Set glass
      </button>
    </div>
  )
}

/**
 * Stubs `matchMedia` so `(prefers-color-scheme: light)` is a stable object (listeners persist
 * across repeated `matchMedia` calls from `resolveColorScheme`).
 */
function stubPrefersColorSchemeLightMedia(initialLight: boolean) {
  const listeners = new Set<() => void>()
  const state = { lightMatches: initialLight }
  const lightQueryList = {
    get matches() {
      return state.lightMatches
    },
    media: '(prefers-color-scheme: light)',
    addEventListener: (_event: string, cb: () => void) => {
      listeners.add(cb)
    },
    removeEventListener: (_event: string, cb: () => void) => {
      listeners.delete(cb)
    },
  }

  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => {
      if (query === '(prefers-color-scheme: light)') {
        return lightQueryList
      }
      if (query === '(prefers-color-scheme: dark)') {
        return {
          get matches() {
            return !state.lightMatches
          },
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }
      }
      return {
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
    })
  )
  return {
    state,
    notify: () => listeners.forEach((listener) => listener()),
  }
}

describe('ColorSchemeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.add('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass', 'pf-v6-theme-high-contrast')
    vi.unstubAllGlobals()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('setColorScheme persists and updates document class', async () => {
    const user = userEvent.setup()
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Set light' }))
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(screen.getByText('Scheme: light')).toBeInTheDocument()
  })

  it('setColorScheme can set dark explicitly', async () => {
    const user = userEvent.setup()
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
    document.documentElement.classList.remove('pf-v6-theme-dark')
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Set dark' }))
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true)
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
  })

  it('toggleColorScheme switches from dark to light', async () => {
    const user = userEvent.setup()
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Toggle' }))
    expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('light')
  })

  it('toggleColorScheme switches between light and dark', async () => {
    const user = userEvent.setup()
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
    document.documentElement.classList.remove('pf-v6-theme-dark')
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Toggle' }))
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true)
  })

  it('syncs from storage event when key matches', async () => {
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    act(() => {
      localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
      globalThis.dispatchEvent(
        new StorageEvent('storage', {
          key: COLOR_SCHEME_STORAGE_KEY,
          newValue: 'light',
          storageArea: localStorage,
        })
      )
    })
    await waitFor(() => {
      expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    })
  })

  it('syncs when storage event key is null after localStorage.clear()', async () => {
    stubPrefersColorSchemeLightMedia(true)
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'dark')
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    act(() => {
      localStorage.clear()
      globalThis.dispatchEvent(
        new StorageEvent('storage', {
          key: null,
          newValue: null,
          storageArea: localStorage,
        })
      )
    })
    await waitFor(() => {
      expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    })
  })

  it('ignores storage events for unrelated keys', () => {
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    act(() => {
      globalThis.dispatchEvent(
        new StorageEvent('storage', {
          key: 'other-key',
          newValue: 'x',
          storageArea: localStorage,
        })
      )
    })
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
  })

  it('applies prefers-color-scheme when no stored preference', async () => {
    const { state, notify } = stubPrefersColorSchemeLightMedia(false)
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    act(() => {
      state.lightMatches = true
      notify()
    })
    await waitFor(() => {
      expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    })
  })

  it('does not apply prefers-color-scheme while explicit preference is stored', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'dark')
    const { state, notify } = stubPrefersColorSchemeLightMedia(true)
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    act(() => {
      state.lightMatches = false
      notify()
    })
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
  })

  it('subscribes safely when matchMedia is undefined', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { unmount } = render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    unmount()
  })

  it('changes contrast without changing the color scheme', async () => {
    const user = userEvent.setup()
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Set high contrast' }))
    expect(screen.getByText('Contrast: high-contrast')).toBeInTheDocument()
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true)
    expect(localStorage.getItem(CONTRAST_MODE_STORAGE_KEY)).toBe('high-contrast')

    await user.click(screen.getByRole('button', { name: 'Set light' }))
    expect(screen.getByText('Scheme: light')).toBeInTheDocument()
    expect(screen.getByText('Contrast: high-contrast')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(true)
  })

  it('keeps an explicit contrast choice when prefers-contrast changes', async () => {
    const user = userEvent.setup()
    const listeners = new Set<() => void>()
    const state = { contrast: false }
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => {
        if (query === '(prefers-contrast: more)') {
          return {
            get matches() {
              return state.contrast
            },
            media: query,
            addEventListener: (_event: string, callback: () => void) => {
              listeners.add(callback)
            },
            removeEventListener: (_event: string, callback: () => void) => {
              listeners.delete(callback)
            },
          }
        }
        return {
          matches: false,
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }
      })
    )
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Set glass' }))
    act(() => {
      state.contrast = true
      listeners.forEach((listener) => listener())
    })
    expect(screen.getByText('Contrast: glass')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(true)
    expect(document.documentElement.classList.contains('pf-v6-theme-high-contrast')).toBe(false)
  })

  it('follows prefers-contrast while the contrast preference is system', async () => {
    const listeners = new Set<() => void>()
    const state = { contrast: false }
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => {
        if (query === '(prefers-contrast: more)') {
          return {
            get matches() {
              return state.contrast
            },
            media: query,
            addEventListener: (_event: string, callback: () => void) => {
              listeners.add(callback)
            },
            removeEventListener: (_event: string, callback: () => void) => {
              listeners.delete(callback)
            },
          }
        }
        return {
          matches: query === '(prefers-color-scheme: dark)',
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }
      })
    )
    render(
      <ColorSchemeProvider>
        <SchemeProbe />
      </ColorSchemeProvider>
    )
    expect(screen.getByText('Contrast preference: system')).toBeInTheDocument()
    act(() => {
      state.contrast = true
      listeners.forEach((listener) => listener())
    })
    await waitFor(() => {
      expect(screen.getByText('Contrast: high-contrast')).toBeInTheDocument()
    })
    expect(screen.getByText('Contrast preference: system')).toBeInTheDocument()
    expect(screen.getByText('Scheme: dark')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(false)
  })
})
