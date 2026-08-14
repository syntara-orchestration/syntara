import { afterEach, describe, expect, it, vi } from 'vitest'

import { isExtendedEnvValue, resolveAppTitleFromEnv } from './buildFlags'

describe('isExtendedEnvValue', () => {
  it('accepts true and 1 only', () => {
    expect(isExtendedEnvValue('true')).toBe(true)
    expect(isExtendedEnvValue('1')).toBe(true)
    expect(isExtendedEnvValue(undefined)).toBe(false)
    expect(isExtendedEnvValue('false')).toBe(false)
    expect(isExtendedEnvValue('yes')).toBe(false)
    expect(isExtendedEnvValue('extended')).toBe(false)
  })
})

describe('resolveAppTitleFromEnv', () => {
  it('always returns Syntara in community builds', () => {
    expect(resolveAppTitleFromEnv({ extended: false, title: 'Custom Extended Title' })).toBe('Syntara')
    expect(resolveAppTitleFromEnv({ extended: false, title: undefined })).toBe('Syntara')
  })

  it('uses VITE_APP_TITLE only when extended', () => {
    expect(resolveAppTitleFromEnv({ extended: true, title: 'Custom Extended Title' })).toBe('Custom Extended Title')
    expect(resolveAppTitleFromEnv({ extended: true, title: undefined })).toBe('Syntara')
    expect(resolveAppTitleFromEnv({ extended: true, title: '  ' })).toBe('Syntara')
  })
})

describe('APP_TITLE module', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('ignores VITE_APP_TITLE when VITE_EXTENDED is unset', async () => {
    vi.stubEnv('VITE_EXTENDED', undefined as unknown as string)
    vi.stubEnv('VITE_APP_TITLE', 'Custom Extended Title')
    vi.resetModules()
    const mod = (await import('./appTitle')) as { APP_TITLE: string }
    expect(mod.APP_TITLE).toBe('Syntara')
  })

  it('uses VITE_APP_TITLE when VITE_EXTENDED=true', async () => {
    vi.stubEnv('VITE_EXTENDED', 'true')
    vi.stubEnv('VITE_APP_TITLE', 'Custom Title')
    vi.resetModules()
    const mod = (await import('./appTitle')) as { APP_TITLE: string }
    expect(mod.APP_TITLE).toBe('Custom Title')
  })

  it('falls back to Syntara when extended but title is missing', async () => {
    vi.stubEnv('VITE_EXTENDED', 'true')
    vi.stubEnv('VITE_APP_TITLE', undefined as unknown as string)
    vi.resetModules()
    const mod = (await import('./appTitle')) as { APP_TITLE: string }
    expect(mod.APP_TITLE).toBe('Syntara')
  })
})

describe('CI upstream mode (VITE_APP_TITLE unset)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('resolves community title when neither VITE_EXTENDED nor VITE_APP_TITLE is set', async () => {
    vi.stubEnv('VITE_EXTENDED', undefined as unknown as string)
    vi.stubEnv('VITE_APP_TITLE', undefined as unknown as string)
    vi.resetModules()
    const mod = (await import('./appTitle')) as { APP_TITLE: string }
    expect(mod.APP_TITLE).toBe('Syntara')
  })

  it('resolveAppTitle returns Syntara with all defaults', async () => {
    vi.stubEnv('VITE_EXTENDED', undefined as unknown as string)
    vi.stubEnv('VITE_APP_TITLE', undefined as unknown as string)
    vi.resetModules()
    const { resolveAppTitle } = (await import('./appTitle')) as {
      resolveAppTitle: (extended?: boolean, title?: string) => string
    }
    expect(resolveAppTitle()).toBe('Syntara')
  })
})
