import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  COLOR_SCHEME_STORAGE_KEY,
  applyDocumentColorScheme,
  ensureDocumentColorScheme,
  readStoredColorSchemePreference,
  resolveColorScheme,
} from './colorScheme'

function mockMatchMedia(light: boolean, dark: boolean) {
  return vi.fn().mockImplementation((query: string) => {
    let matches = false
    if (query === '(prefers-color-scheme: light)') {
      matches = light
    } else if (query === '(prefers-color-scheme: dark)') {
      matches = dark
    }
    return {
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }
  })
}

describe('colorScheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.add('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass')
    vi.unstubAllGlobals()
  })

  it('readStoredColorSchemePreference returns null for unknown values', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'sepia')
    expect(readStoredColorSchemePreference()).toBeNull()
  })

  it('readStoredColorSchemePreference accepts system', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'system')
    expect(readStoredColorSchemePreference()).toBe('system')
  })

  it('resolveColorScheme follows media when the stored preference is system', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia(true, false))
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'system')
    expect(resolveColorScheme()).toBe('light')
  })

  it('resolveColorScheme returns stored light', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
    expect(resolveColorScheme()).toBe('light')
  })

  it('resolveColorScheme prefers stored value over media', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia(true, false))
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'dark')
    expect(resolveColorScheme()).toBe('dark')
  })

  it('resolveColorScheme uses light media when nothing stored', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia(true, false))
    expect(resolveColorScheme()).toBe('light')
  })

  it('resolveColorScheme uses dark media when nothing stored', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia(false, true))
    expect(resolveColorScheme()).toBe('dark')
  })

  it('resolveColorScheme defaults to dark when no stored preference and no-preference media', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia(false, false))
    expect(resolveColorScheme()).toBe('dark')
  })

  it('applyDocumentColorScheme toggles pf-v6-theme-dark only; pf-v6-theme-glass stays for both schemes', () => {
    applyDocumentColorScheme('light')
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(true)
    applyDocumentColorScheme('dark')
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true)
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(true)
  })

  it('ensureDocumentColorScheme applies resolved scheme', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
    ensureDocumentColorScheme()
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(document.documentElement.classList.contains('pf-v6-theme-glass')).toBe(true)
  })
})
