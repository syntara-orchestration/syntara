// Flat path map + community homepage. Optional *.overlay.json may add productBaseUrl
// and/or path overrides (merged over the base map).

import { z } from 'zod'

import baseDocsConfig from './docsConfig.json' with { type: 'json' }
import baseDocsUrls from './docsUrls.json' with { type: 'json' }

// Stryker disable all: Vite needs static glob arguments before test transforms run.
const overlayConfigModules = import.meta.glob('./docsConfig.overlay.json', {
  eager: true,
  import: 'default',
})
// Stryker restore all

// Stryker disable all: Vite needs static glob arguments before test transforms run.
const overlayUrlsModules = import.meta.glob('./docsUrls.overlay.json', {
  eager: true,
  import: 'default',
})
// Stryker restore all

/** Overlay may set product base / version only — never communityBaseUrl. */
const docsConfigOverlaySchema = z
  .object({
    productBaseUrl: z.string().min(1).optional(),
    version: z.string().min(1).optional(),
  })
  .strict()

const docsUrlsOverlaySchema = z.record(z.string(), z.string())

export type DocsConfig = {
  communityBaseUrl: string
  productBaseUrl?: string
  version: string
}

type DocsConfigOverlay = z.infer<typeof docsConfigOverlaySchema>

/** Parse overlay config; throws if shape is invalid (fails the build/module load). */
export function parseDocsConfigOverlay(raw: unknown): DocsConfigOverlay | undefined {
  if (raw === undefined) {
    return undefined
  }
  return docsConfigOverlaySchema.parse(raw)
}

/** Parse overlay URL map; throws if shape is invalid. */
export function parseDocsUrlsOverlay(raw: unknown): Record<string, string> | undefined {
  if (raw === undefined) {
    return undefined
  }
  return docsUrlsOverlaySchema.parse(raw)
}

/**
 * Merge base + overlay. Overlay can add productBaseUrl and override version,
 * but cannot clobber communityBaseUrl.
 */
export function mergeDocsConfig(base: typeof baseDocsConfig, overlay: DocsConfigOverlay | undefined): DocsConfig {
  return {
    communityBaseUrl: base.communityBaseUrl,
    version: overlay?.version ?? base.version,
    ...(overlay?.productBaseUrl ? { productBaseUrl: overlay.productBaseUrl } : {}),
  }
}

/** Overlay paths win per key; missing keys keep the base paths (merge, not full replace). */
export function mergeDocsUrls(
  base: Record<string, string>,
  overlay: Record<string, string> | undefined
): Record<string, string> {
  return {
    ...base,
    ...overlay,
  }
}

const overlayConfig = parseDocsConfigOverlay(overlayConfigModules['./docsConfig.overlay.json'])
const overlayUrls = parseDocsUrlsOverlay(overlayUrlsModules['./docsUrls.overlay.json'])

export const docsConfig: DocsConfig = mergeDocsConfig(baseDocsConfig, overlayConfig)

export const docsUrls: Record<string, string> = mergeDocsUrls(baseDocsUrls, overlayUrls)
