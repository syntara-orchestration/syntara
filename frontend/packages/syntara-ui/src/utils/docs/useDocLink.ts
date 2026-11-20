import { use } from 'react'

import { isCommunityMode, type AppMode } from '../appMode'

import { DocLinkContext } from './docLinkContext'
import { docsConfig, docsUrls, type DocsConfig } from './loadDocsConfig'
import type { DocKey, DocsUrlMap } from './types'

/**
 * Pure resolver: community (or missing product base) → configured per-page path
 * or community homepage; extended with
 * productBaseUrl → base + path. Use this from hooks and tests.
 */
export function resolveDocUrl(
  key: DocKey,
  options: {
    mode: AppMode
    version: string
    config?: DocsConfig
    urls?: DocsUrlMap
  }
): string {
  const config = options.config ?? docsConfig
  const urls = options.urls ?? (docsUrls as DocsUrlMap)

  if (isCommunityMode(options.mode) || !config.productBaseUrl) {
    const communityPath = config.communityPaths?.[key]
    return communityPath ? new URL(communityPath, config.communityBaseUrl).href : config.communityBaseUrl
  }

  const resolvedBase = config.productBaseUrl.replace('{version}', options.version)
  const base = resolvedBase.endsWith('/') ? resolvedBase : `${resolvedBase}/`
  const rawPath = (urls[key] ?? urls.home ?? '').replace(/^\/+/, '')
  return new URL(rawPath, base).href
}

/** Hook wrapper around {@link resolveDocUrl}. */
export function useDocLink(key: DocKey): string {
  const { mode, version } = use(DocLinkContext)

  return resolveDocUrl(key, { mode, version })
}
