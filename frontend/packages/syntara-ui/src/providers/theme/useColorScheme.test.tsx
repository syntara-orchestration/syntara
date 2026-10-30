import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ColorSchemeProvider } from './ColorSchemeProvider'
import { useColorScheme } from './useColorScheme'

function wrapper({ children }: { children: ReactNode }) {
  return <ColorSchemeProvider>{children}</ColorSchemeProvider>
}

describe('useColorScheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.add('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  it('throws when used outside ColorSchemeProvider', () => {
    expect(() => {
      renderHook(() => useColorScheme())
    }).toThrow('useColorScheme must be used within ColorSchemeProvider')
  })

  it('returns color scheme and controls inside ColorSchemeProvider', () => {
    const { result } = renderHook(() => useColorScheme(), { wrapper })

    expect(result.current.colorScheme).toBe('dark')
    expect(typeof result.current.setColorScheme).toBe('function')
    expect(typeof result.current.toggleColorScheme).toBe('function')
    expect(typeof result.current.setContrastMode).toBe('function')
    expect(result.current.contrastMode).toBe('glass')
    expect(result.current.contrastPreference).toBe('system')
    expect(result.current.colorSchemePreference).toBe('system')
  })
})
