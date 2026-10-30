import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  COLOR_SCHEME_STORAGE_KEY,
  type ColorScheme,
  type ColorSchemePreference,
  applyDocumentColorScheme,
  colorSchemeFollowsSystem,
  getColorSchemeFromDocument,
  persistColorScheme,
  readStoredColorSchemePreference,
  resolveColorScheme,
} from './colorScheme'
import { ColorSchemeContext } from './colorSchemeReactContext'
import {
  CONTRAST_MODE_STORAGE_KEY,
  FORCED_COLORS_QUERY,
  PREFERS_CONTRAST_QUERY,
  PREFERS_REDUCED_TRANSPARENCY_QUERY,
  type ContrastMode,
  type ContrastPreference,
  applyDocumentContrast,
  contrastFollowsSystem,
  getContrastModeFromDocument,
  persistContrastPreference,
  readStoredContrastPreference,
  resolveContrastMode,
} from './contrastMode'

function preferenceOrSystem(preference: ColorSchemePreference | null): ColorSchemePreference {
  return preference ?? 'system'
}

function contrastPreferenceOrSystem(preference: ContrastPreference | null): ContrastPreference {
  return preference ?? 'system'
}

/**
 * Provides persisted color-scheme and contrast-mode state, syncs `document.documentElement`,
 * and listens for cross-tab `storage` events. OS media queries apply only while that setting
 * is `system` (or unset).
 */
export function ColorSchemeProvider(props: Readonly<{ children: ReactNode }>) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>(() => getColorSchemeFromDocument())
  const [colorSchemePreference, setColorSchemePreference] = useState<ColorSchemePreference>(() =>
    preferenceOrSystem(readStoredColorSchemePreference())
  )
  const [contrastMode, setContrastModeState] = useState<ContrastMode>(() => getContrastModeFromDocument())
  const [contrastPreference, setContrastPreference] = useState<ContrastPreference>(() =>
    contrastPreferenceOrSystem(readStoredContrastPreference())
  )

  const commitColorScheme = useCallback((preference: ColorSchemePreference) => {
    persistColorScheme(preference)
    const resolved = resolveColorScheme()
    applyDocumentColorScheme(resolved)
    setColorSchemePreference(preference)
    setColorSchemeState(resolved)
  }, [])

  const commitContrastMode = useCallback((preference: ContrastPreference) => {
    persistContrastPreference(preference)
    const resolved = resolveContrastMode()
    applyDocumentContrast(resolved)
    setContrastPreference(preference)
    setContrastModeState(resolved)
  }, [])

  const toggleColorScheme = useCallback(() => {
    commitColorScheme(colorScheme === 'dark' ? 'light' : 'dark')
  }, [colorScheme, commitColorScheme])

  useEffect(() => {
    const syncColorScheme = () => {
      const preference = preferenceOrSystem(readStoredColorSchemePreference())
      const resolved = resolveColorScheme()
      applyDocumentColorScheme(resolved)
      setColorSchemePreference(preference)
      setColorSchemeState(resolved)
    }

    const syncContrast = () => {
      const preference = contrastPreferenceOrSystem(readStoredContrastPreference())
      const resolved = resolveContrastMode()
      applyDocumentContrast(resolved)
      setContrastPreference(preference)
      setContrastModeState(resolved)
    }

    const onStorage = (event: StorageEvent) => {
      if (event.key !== null && event.key !== COLOR_SCHEME_STORAGE_KEY && event.key !== CONTRAST_MODE_STORAGE_KEY) {
        return
      }
      if (event.key === null || event.key === COLOR_SCHEME_STORAGE_KEY) {
        syncColorScheme()
      }
      if (event.key === null || event.key === CONTRAST_MODE_STORAGE_KEY) {
        syncContrast()
      }
    }

    const onMediaChange = () => {
      if (colorSchemeFollowsSystem()) {
        const resolved = resolveColorScheme()
        applyDocumentColorScheme(resolved)
        setColorSchemeState(resolved)
      }
      if (contrastFollowsSystem()) {
        const resolved = resolveContrastMode()
        applyDocumentContrast(resolved)
        setContrastModeState(resolved)
      }
    }

    const queries = [
      '(prefers-color-scheme: light)',
      PREFERS_CONTRAST_QUERY,
      FORCED_COLORS_QUERY,
      PREFERS_REDUCED_TRANSPARENCY_QUERY,
    ]
    const mediaLists: MediaQueryList[] = []
    for (const query of queries) {
      try {
        const media = globalThis.matchMedia?.(query)
        if (media) {
          mediaLists.push(media)
        }
      } catch {
        // matchMedia may be unavailable.
      }
    }

    globalThis.addEventListener('storage', onStorage)
    for (const media of mediaLists) {
      media.addEventListener('change', onMediaChange)
    }
    return () => {
      globalThis.removeEventListener('storage', onStorage)
      for (const media of mediaLists) {
        media.removeEventListener('change', onMediaChange)
      }
    }
  }, [])

  const value = useMemo(
    () => ({
      colorScheme,
      colorSchemePreference,
      setColorScheme: commitColorScheme,
      toggleColorScheme,
      contrastMode,
      contrastPreference,
      setContrastMode: commitContrastMode,
    }),
    [
      colorScheme,
      colorSchemePreference,
      commitColorScheme,
      toggleColorScheme,
      contrastMode,
      contrastPreference,
      commitContrastMode,
    ]
  )

  return <ColorSchemeContext.Provider value={value}>{props.children}</ColorSchemeContext.Provider>
}
