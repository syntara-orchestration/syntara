import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { COLOR_SCHEME_STORAGE_KEY } from './colorScheme'
import {
  CONTRAST_MODE_STORAGE_KEY,
  FORCED_COLORS_QUERY,
  GLASS_CLASS,
  HIGH_CONTRAST_CLASS,
  PREFERS_CONTRAST_QUERY,
  PREFERS_REDUCED_TRANSPARENCY_QUERY,
  applyDocumentContrast,
  getContrastModeFromDocument,
  readStoredContrastPreference,
  resolveContrastMode,
} from './contrastMode'
import { ensureDocumentTheme } from './documentTheme'

function mockMatchMedia(matches: Record<string, boolean>) {
  return vi.fn().mockImplementation((query: string) => ({
    matches: matches[query] ?? false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

describe('contrastMode', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', HIGH_CONTRAST_CLASS, GLASS_CLASS)
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', HIGH_CONTRAST_CLASS, GLASS_CLASS)
    vi.unstubAllGlobals()
  })

  it('readStoredContrastPreference rejects unknown values', () => {
    localStorage.setItem(CONTRAST_MODE_STORAGE_KEY, 'sepia')
    expect(readStoredContrastPreference()).toBeNull()
  })

  it('resolveContrastMode uses an explicit choice over OS contrast', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia({ [PREFERS_CONTRAST_QUERY]: true }))
    localStorage.setItem(CONTRAST_MODE_STORAGE_KEY, 'glass')
    expect(resolveContrastMode()).toBe('glass')
  })

  it('resolveContrastMode uses high contrast for prefers-contrast and forced colors', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia({ [PREFERS_CONTRAST_QUERY]: true, [FORCED_COLORS_QUERY]: false }))
    expect(resolveContrastMode()).toBe('high-contrast')
    vi.stubGlobal('matchMedia', mockMatchMedia({ [FORCED_COLORS_QUERY]: true }))
    expect(resolveContrastMode()).toBe('high-contrast')
  })

  it('resolveContrastMode uses default contrast for reduced transparency', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia({ [PREFERS_REDUCED_TRANSPARENCY_QUERY]: true }))
    expect(resolveContrastMode()).toBe('default')
  })

  it('resolveContrastMode prefers high contrast over reduced transparency', () => {
    vi.stubGlobal(
      'matchMedia',
      mockMatchMedia({
        [PREFERS_CONTRAST_QUERY]: true,
        [PREFERS_REDUCED_TRANSPARENCY_QUERY]: true,
      })
    )
    expect(resolveContrastMode()).toBe('high-contrast')
  })

  it('resolveContrastMode defaults to glass when the OS does not request a contrast change', () => {
    vi.stubGlobal('matchMedia', mockMatchMedia({}))
    expect(resolveContrastMode()).toBe('glass')
  })

  it('applyDocumentContrast keeps glass and high contrast mutually exclusive', () => {
    applyDocumentContrast('high-contrast')
    expect(document.documentElement.classList.contains(HIGH_CONTRAST_CLASS)).toBe(true)
    expect(document.documentElement.classList.contains(GLASS_CLASS)).toBe(false)
    applyDocumentContrast('glass')
    expect(document.documentElement.classList.contains(HIGH_CONTRAST_CLASS)).toBe(false)
    expect(document.documentElement.classList.contains(GLASS_CLASS)).toBe(true)
    applyDocumentContrast('default')
    expect(document.documentElement.classList.contains(HIGH_CONTRAST_CLASS)).toBe(false)
    expect(document.documentElement.classList.contains(GLASS_CLASS)).toBe(false)
    expect(getContrastModeFromDocument()).toBe('default')
  })

  it('getContrastModeFromDocument prefers high contrast when both classes are present', () => {
    document.documentElement.classList.add(HIGH_CONTRAST_CLASS, GLASS_CLASS)
    expect(getContrastModeFromDocument()).toBe('high-contrast')
  })

  it('ensureDocumentTheme applies color and contrast together', () => {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'light')
    localStorage.setItem(CONTRAST_MODE_STORAGE_KEY, 'high-contrast')
    ensureDocumentTheme()
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(document.documentElement.classList.contains(HIGH_CONTRAST_CLASS)).toBe(true)
    expect(document.documentElement.classList.contains(GLASS_CLASS)).toBe(false)
  })

  it('index.html bootstrap uses the same storage keys and contrast signals', () => {
    const indexHtml = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../index.html'), 'utf8')
    expect(indexHtml).toContain(COLOR_SCHEME_STORAGE_KEY)
    expect(indexHtml).toContain(CONTRAST_MODE_STORAGE_KEY)
    expect(indexHtml).toContain(HIGH_CONTRAST_CLASS)
    expect(indexHtml).toContain(GLASS_CLASS)
    expect(indexHtml).toContain(PREFERS_CONTRAST_QUERY)
    expect(indexHtml).toContain(FORCED_COLORS_QUERY)
    expect(indexHtml).toContain(PREFERS_REDUCED_TRANSPARENCY_QUERY)
    expect(indexHtml).toContain('pf-v6-theme-dark')
  })
})
