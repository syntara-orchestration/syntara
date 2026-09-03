import { describe, expect, it } from 'vitest'

import {
  ROUTE_MANIFEST_COMMENT_KEY,
  ROUTE_MANIFEST_NOTICE,
  routeManifestSchema,
} from './route-manifest-schema'

const validManifest = {
  [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
  version: 1 as const,
  routes: [
    {
      template: '/workflows',
      parameters: [],
      kind: 'page' as const,
      sources: ['router'] as const,
    },
  ],
}

describe('routeManifestSchema', () => {
  it('accepts a valid manifest and infers the typed shape', () => {
    const parsed = routeManifestSchema.parse(validManifest)

    expect(parsed.version).toBe(1)
    expect(parsed[ROUTE_MANIFEST_COMMENT_KEY]).toBe(ROUTE_MANIFEST_NOTICE)
    expect(parsed.routes[0]?.template).toBe('/workflows')
  })

  it('rejects a missing do-not-edit banner', () => {
    const result = routeManifestSchema.safeParse({
      version: 1,
      routes: validManifest.routes,
    })

    expect(result.success).toBe(false)
  })

  it('rejects an unknown route kind', () => {
    const result = routeManifestSchema.safeParse({
      ...validManifest,
      routes: [{ ...validManifest.routes[0], kind: 'mystery' }],
    })

    expect(result.success).toBe(false)
  })

  it('rejects a non-literal schema version', () => {
    const result = routeManifestSchema.safeParse({
      ...validManifest,
      version: 2,
    })

    expect(result.success).toBe(false)
  })
})
