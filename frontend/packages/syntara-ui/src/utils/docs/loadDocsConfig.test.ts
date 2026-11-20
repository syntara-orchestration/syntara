import { describe, expect, it } from 'vitest'

import baseDocsConfig from './docsConfig.json' with { type: 'json' }
import baseDocsUrls from './docsUrls.json' with { type: 'json' }
import { mergeDocsConfig, mergeDocsUrls, parseDocsConfigOverlay, parseDocsUrlsOverlay } from './loadDocsConfig'

describe('loadDocsConfig (no overlay)', () => {
  it('mergeDocsConfig without overlay omits productBaseUrl', () => {
    const config = mergeDocsConfig(baseDocsConfig, undefined)
    expect(config).toEqual({
      communityBaseUrl: baseDocsConfig.communityBaseUrl,
      communityPaths: baseDocsConfig.communityPaths,
      version: baseDocsConfig.version,
    })
    expect(config.productBaseUrl).toBeUndefined()
  })

  it('mergeDocsUrls without overlay returns base unchanged', () => {
    expect(mergeDocsUrls(baseDocsUrls, undefined)).toEqual(baseDocsUrls)
  })
})

describe('parseDocsConfigOverlay', () => {
  it('returns undefined when overlay is absent', () => {
    expect(parseDocsConfigOverlay(undefined)).toBeUndefined()
  })

  it('accepts productBaseUrl and version', () => {
    expect(
      parseDocsConfigOverlay({
        productBaseUrl: 'https://example.invalid/docs/{version}/',
        version: '2.5',
      })
    ).toEqual({
      productBaseUrl: 'https://example.invalid/docs/{version}/',
      version: '2.5',
    })
  })

  it('rejects communityBaseUrl so overlays cannot clobber the community fallback', () => {
    expect(() =>
      parseDocsConfigOverlay({
        communityBaseUrl: 'https://evil.example/',
        productBaseUrl: 'https://example.invalid/docs/{version}/',
      })
    ).toThrow()
  })

  it('rejects unknown keys', () => {
    expect(() => parseDocsConfigOverlay({ productbaseurl: 'https://typo.example/' })).toThrow()
  })
})

describe('parseDocsUrlsOverlay', () => {
  it('returns undefined when overlay is absent', () => {
    expect(parseDocsUrlsOverlay(undefined)).toBeUndefined()
  })

  it('accepts a string map', () => {
    expect(parseDocsUrlsOverlay({ workflows: '__PLACEHOLDER__/workflows' })).toEqual({
      workflows: '__PLACEHOLDER__/workflows',
    })
  })

  it('rejects non-string values', () => {
    expect(() => parseDocsUrlsOverlay({ workflows: 1 })).toThrow()
  })
})

describe('mergeDocsConfig', () => {
  it('keeps communityBaseUrl from base even if overlay somehow had other fields', () => {
    const merged = mergeDocsConfig(baseDocsConfig, {
      productBaseUrl: 'https://example.invalid/docs/{version}/',
      version: '9.9',
    })

    expect(merged.communityBaseUrl).toBe(baseDocsConfig.communityBaseUrl)
    expect(merged.productBaseUrl).toBe('https://example.invalid/docs/{version}/')
    expect(merged.version).toBe('9.9')
  })

  it('omits productBaseUrl when overlay does not set it', () => {
    expect(mergeDocsConfig(baseDocsConfig, { version: '3.0' }).productBaseUrl).toBeUndefined()
  })
})

describe('mergeDocsUrls', () => {
  it('lets overlay paths win per key and keeps missing keys from base', () => {
    expect(
      mergeDocsUrls({ home: 'base-home', workflows: 'base-workflows' }, { workflows: '__PLACEHOLDER__/workflows' })
    ).toEqual({
      home: 'base-home',
      workflows: '__PLACEHOLDER__/workflows',
    })
  })
})
