/**
 * Contrast mode: PatternFly applies one of default (no extra class), `pf-v6-theme-high-contrast`,
 * or `pf-v6-theme-glass` on `<html>`. The classes are mutually exclusive. PatternFly styles conflict
 * when glass and high contrast are both present.
 * Keep `resolveContrastMode` and `applyDocumentContrast` in sync with the inline script in `index.html`.
 *
 * With no stored choice, the product shell stays glass unless the OS asks for more contrast,
 * forced colors, or reduced transparency. An explicit choice overrides the OS.
 */
/** `localStorage` key for the contrast-mode preference. */
export const CONTRAST_MODE_STORAGE_KEY = 'syntara-ui-contrast-mode'

export const HIGH_CONTRAST_CLASS = 'pf-v6-theme-high-contrast'
export const GLASS_CLASS = 'pf-v6-theme-glass'

export const PREFERS_CONTRAST_QUERY = '(prefers-contrast: more)'
export const FORCED_COLORS_QUERY = '(forced-colors: active)'
export const PREFERS_REDUCED_TRANSPARENCY_QUERY = '(prefers-reduced-transparency: reduce)'

/** Resolved contrast class on `<html>`. */
export type ContrastMode = 'default' | 'high-contrast' | 'glass'

/** User choice. `system` follows OS contrast, forced colors, and reduced transparency. */
export type ContrastPreference = 'system' | ContrastMode

function mediaMatches(query: string): boolean {
  try {
    return globalThis.matchMedia?.(query).matches ?? false
  } catch {
    return false
  }
}

/** Returns a valid stored preference, or `null` if missing, invalid, or storage is unavailable. */
export function readStoredContrastPreference(): ContrastPreference | null {
  try {
    const value = globalThis.localStorage?.getItem(CONTRAST_MODE_STORAGE_KEY)
    if (value === 'system' || value === 'default' || value === 'high-contrast' || value === 'glass') {
      return value
    }
  } catch {
    // Storage may be unavailable (private mode, SSR).
  }
  return null
}

/**
 * Effective contrast: explicit preference, else OS signals, else glass (the product shell).
 * `prefers-contrast: more` and `forced-colors: active` win over reduced transparency.
 * Must stay aligned with `index.html` inline bootstrap script.
 */
export function resolveContrastMode(): ContrastMode {
  const stored = readStoredContrastPreference()
  if (stored === 'default' || stored === 'high-contrast' || stored === 'glass') {
    return stored
  }
  if (mediaMatches(PREFERS_CONTRAST_QUERY) || mediaMatches(FORCED_COLORS_QUERY)) {
    return 'high-contrast'
  }
  if (mediaMatches(PREFERS_REDUCED_TRANSPARENCY_QUERY)) {
    return 'default'
  }
  return 'glass'
}

/** True when contrast should track the OS, including when nothing is stored yet. */
export function contrastFollowsSystem(): boolean {
  const stored = readStoredContrastPreference()
  return stored === null || stored === 'system'
}

/** Reads the active contrast mode from `document.documentElement`. High contrast wins if both classes are set. */
export function getContrastModeFromDocument(): ContrastMode {
  const root = document.documentElement
  if (root.classList.contains(HIGH_CONTRAST_CLASS)) {
    return 'high-contrast'
  }
  if (root.classList.contains(GLASS_CLASS)) {
    return 'glass'
  }
  return 'default'
}

/**
 * Applies exactly one contrast treatment. Clears both theme classes for default.
 */
export function applyDocumentContrast(mode: ContrastMode): void {
  const root = document.documentElement
  root.classList.toggle(HIGH_CONTRAST_CLASS, mode === 'high-contrast')
  root.classList.toggle(GLASS_CLASS, mode === 'glass')
}

/** Writes `preference` to `localStorage` under {@link CONTRAST_MODE_STORAGE_KEY}; no-ops if storage fails. */
export function persistContrastPreference(preference: ContrastPreference): void {
  try {
    globalThis.localStorage?.setItem(CONTRAST_MODE_STORAGE_KEY, preference)
  } catch {
    // ignore
  }
}
