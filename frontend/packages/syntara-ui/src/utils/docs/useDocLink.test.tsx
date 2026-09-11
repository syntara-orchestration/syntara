import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { DocLinkProvider } from './DocLinkProvider'
import docsUrls from './docsUrls.json' with { type: 'json' }
import type { DocKey } from './types'
import { resolveDocUrl, useDocLink } from './useDocLink'

vi.mock('./loadDocsConfig', async (importOriginal) => {
  const base = await import('./docsConfig.json')
  const actual = await importOriginal<typeof import('./loadDocsConfig')>()
  return {
    ...actual,
    docsConfig: {
      communityBaseUrl: base.default.communityBaseUrl,
      version: base.default.version,
    },
  }
})

const COMMUNITY_README = 'https://github.com/syntara-orchestration/syntara/blob/devel/README.md'

const PRODUCT_BASE = 'https://example.invalid/docs/{version}/'

function wrapper({ children }: Readonly<{ children: ReactNode }>) {
  return <DocLinkProvider>{children}</DocLinkProvider>
}

const allDocKeys = Object.keys(docsUrls) as DocKey[]

describe('resolveDocUrl', () => {
  it('returns community homepage in community mode', () => {
    expect(
      resolveDocUrl('workflows', {
        mode: 'community',
        version: '2.5',
        config: { communityBaseUrl: COMMUNITY_README, version: '2.5' },
        urls: docsUrls,
      })
    ).toBe(COMMUNITY_README)
  })

  it('falls back to community homepage in extended mode without productBaseUrl', () => {
    expect(
      resolveDocUrl('workflows', {
        mode: 'extended',
        version: '2.5',
        config: { communityBaseUrl: COMMUNITY_README, version: '2.5' },
        urls: docsUrls,
      })
    ).toBe(COMMUNITY_README)
  })

  it('uses productBaseUrl + path in extended mode when productBaseUrl is set', () => {
    expect(
      resolveDocUrl('workflows', {
        mode: 'extended',
        version: '2.5',
        config: {
          communityBaseUrl: COMMUNITY_README,
          productBaseUrl: PRODUCT_BASE,
          version: '2.5',
        },
        urls: {
          home: '__PLACEHOLDER__/',
          workflows: '__PLACEHOLDER__/workflows',
        } as Record<DocKey, string>,
      })
    ).toBe('https://example.invalid/docs/2.5/__PLACEHOLDER__/workflows')
  })

  it('normalizes productBaseUrl missing trailing slash', () => {
    expect(
      resolveDocUrl('workflows', {
        mode: 'extended',
        version: '2.5',
        config: {
          communityBaseUrl: COMMUNITY_README,
          productBaseUrl: 'https://example.invalid/docs/{version}',
          version: '2.5',
        },
        urls: { home: '', workflows: 'workflows' } as Record<DocKey, string>,
      })
    ).toBe('https://example.invalid/docs/2.5/workflows')
  })

  it('normalizes path with leading slash', () => {
    expect(
      resolveDocUrl('workflows', {
        mode: 'extended',
        version: '2.5',
        config: {
          communityBaseUrl: COMMUNITY_README,
          productBaseUrl: PRODUCT_BASE,
          version: '2.5',
        },
        urls: { home: '', workflows: '/workflows' } as Record<DocKey, string>,
      })
    ).toBe('https://example.invalid/docs/2.5/workflows')
  })
})

describe('useDocLink', () => {
  it('returns community README by default', () => {
    const { result } = renderHook(() => useDocLink('workflows'), { wrapper })

    expect(result.current).toBe(COMMUNITY_README)
  })

  it('returns community README for every key', () => {
    expect.assertions(allDocKeys.length)
    for (const key of allDocKeys) {
      const { result } = renderHook(() => useDocLink(key), { wrapper })
      expect(result.current).toBe(COMMUNITY_README)
    }
  })

  it('falls back to community README in extended mode when productBaseUrl is absent', () => {
    vi.stubEnv('VITE_EXTENDED', 'true')

    const { result } = renderHook(() => useDocLink('workflows'), { wrapper })

    expect(result.current).toBe(COMMUNITY_README)

    vi.unstubAllEnvs()
  })
})
