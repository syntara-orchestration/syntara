import { describe, expect, it } from 'vitest'

import { diffRouteManifest } from './diff-route-manifest'
import { ROUTE_MANIFEST_COMMENT_KEY, ROUTE_MANIFEST_NOTICE, type RouteManifest } from './route-manifest-schema'

const base: RouteManifest = {
  [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
  version: 1,
  routes: [
    {
      template: '/workflows',
      parameters: [],
      kind: 'page',
      sources: ['router'],
    },
    {
      template: '/workflows/$workflowId',
      parameters: ['workflowId'],
      kind: 'page',
      sources: ['router'],
    },
  ],
}

describe('diffRouteManifest', () => {
  it('reports additions, removals, and parameter renames as changes', () => {
    const next: RouteManifest = {
      [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
      version: 1,
      routes: [
        {
          template: '/flows',
          parameters: [],
          kind: 'page',
          sources: ['router'],
        },
        {
          template: '/workflows/$id',
          parameters: ['id'],
          kind: 'page',
          sources: ['router'],
        },
      ],
    }

    expect(diffRouteManifest(base, next)).toStrictEqual({
      added: ['/flows', '/workflows/$id'],
      removed: ['/workflows', '/workflows/$workflowId'],
      changed: [],
    })
  })

  it('reports in-place kind or parameter list changes', () => {
    const next: RouteManifest = {
      [ROUTE_MANIFEST_COMMENT_KEY]: ROUTE_MANIFEST_NOTICE,
      version: 1,
      routes: [
        {
          template: '/workflows',
          parameters: [],
          kind: 'redirect',
          redirectTo: '/elsewhere',
          sources: ['router'],
        },
        base.routes[1],
      ],
    }

    const diff = diffRouteManifest(base, next)
    expect(diff.added).toStrictEqual([])
    expect(diff.removed).toStrictEqual([])
    expect(diff.changed).toHaveLength(1)
    expect(diff.changed[0]?.template).toBe('/workflows')
  })
})
