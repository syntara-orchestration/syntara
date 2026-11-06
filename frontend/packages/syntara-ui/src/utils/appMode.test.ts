import { afterEach, describe, expect, it, vi } from 'vitest'

import { isCommunityMode, isExtendedMode, resolveAppMode } from './appMode'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('resolveAppMode', () => {
  it('returns community when VITE_EXTENDED is unset', () => {
    vi.stubEnv('VITE_EXTENDED', undefined)

    expect(resolveAppMode()).toBe('community')
  })

  it('returns extended when VITE_EXTENDED=true', () => {
    vi.stubEnv('VITE_EXTENDED', 'true')

    expect(resolveAppMode()).toBe('extended')
  })

  it('returns extended when VITE_EXTENDED=1', () => {
    vi.stubEnv('VITE_EXTENDED', '1')

    expect(resolveAppMode()).toBe('extended')
  })

  it('returns community for other string values (typo-safe)', () => {
    vi.stubEnv('VITE_EXTENDED', 'yes')

    expect(resolveAppMode()).toBe('community')
  })

  it('ignores legacy VITE_DOC_MODE / VITE_APP_MODE (use VITE_EXTENDED)', () => {
    vi.stubEnv('VITE_DOC_MODE', 'product')
    vi.stubEnv('VITE_APP_MODE', 'product')

    expect(resolveAppMode()).toBe('community')

    vi.stubEnv('VITE_EXTENDED', 'true')
    expect(resolveAppMode()).toBe('extended')
  })
})

describe('isCommunityMode / isExtendedMode', () => {
  it('classifies an explicit mode without reading env', () => {
    expect(isCommunityMode('community')).toBe(true)
    expect(isExtendedMode('community')).toBe(false)
    expect(isCommunityMode('extended')).toBe(false)
    expect(isExtendedMode('extended')).toBe(true)
  })

  it('defaults to resolveAppMode() when mode is omitted', () => {
    vi.stubEnv('VITE_EXTENDED', undefined)

    expect(isCommunityMode()).toBe(true)
    expect(isExtendedMode()).toBe(false)

    vi.stubEnv('VITE_EXTENDED', 'true')

    expect(isCommunityMode()).toBe(false)
    expect(isExtendedMode()).toBe(true)
  })
})
