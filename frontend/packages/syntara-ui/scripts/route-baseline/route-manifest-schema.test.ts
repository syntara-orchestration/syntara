import { describe, expect, it } from 'vitest'

import {
  ROUTE_MANIFEST_COMMENT_KEY,
  ROUTE_MANIFEST_NOTICE,
  absolutePathSchema,
  parsedCreateRouteSchema,
  plainObjectSchema,
  routeManifestJsonSchema,
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

describe('plainObjectSchema', () => {
  it('accepts plain objects and rejects null, arrays, and primitives', () => {
    expect(plainObjectSchema.safeParse({ a: 1 }).success).toBe(true)
    expect(plainObjectSchema.safeParse(null).success).toBe(false)
    expect(plainObjectSchema.safeParse([]).success).toBe(false)
    expect(plainObjectSchema.safeParse('x').success).toBe(false)
  })
})

describe('absolutePathSchema', () => {
  it('requires a leading slash', () => {
    expect(absolutePathSchema.safeParse('/workflows').success).toBe(true)
    expect(absolutePathSchema.safeParse('workflows').success).toBe(false)
    expect(absolutePathSchema.safeParse('').success).toBe(false)
  })
})

describe('parsedCreateRouteSchema', () => {
  it('accepts page and redirect shapes', () => {
    expect(parsedCreateRouteSchema.parse({ path: '/workflows', kind: 'page' })).toStrictEqual({
      path: '/workflows',
      kind: 'page',
    })
    expect(
      parsedCreateRouteSchema.parse({
        path: '/configuration',
        kind: 'redirect',
        redirectTo: '/configuration/integrations',
      })
    ).toMatchObject({ kind: 'redirect', redirectTo: '/configuration/integrations' })
  })
})

describe('routeManifestJsonSchema', () => {
  it('parses JSON text into a typed manifest', () => {
    const parsed = routeManifestJsonSchema.parse(JSON.stringify(validManifest))
    expect(parsed).toStrictEqual(validManifest)
  })

  it('rejects invalid JSON text', () => {
    expect(routeManifestJsonSchema.safeParse('{not-json').success).toBe(false)
  })
})
