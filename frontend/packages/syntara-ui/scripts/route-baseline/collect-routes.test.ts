import { describe, expect, it } from 'vitest'

import {
  collectAppLevelRoutesFromSource,
  collectFallbackRouteFromSource,
  collectNavigationPathsFromSource,
  collectPathsFromObject,
  extractBalancedObjectBody,
  parseAppRouteCatalog,
  parseCreateRouteBlocks,
  parseMountedRouteModules,
  resolveAppRouteReference,
} from './collect-routes'

describe('parseCreateRouteBlocks', () => {
  it('extracts page routes', () => {
    const source = `
export const routes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/workflows',
    component: makeRouteComponent(<Workflows />),
  }),
]
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([{ path: '/workflows', kind: 'page' }])
  })

  it('detects redirect routes and destination', () => {
    const source = `
export const routes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/configuration',
    beforeLoad: () => redirect({ to: '/configuration/integrations', replace: true }),
  }),
]
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([
      {
        path: '/configuration',
        kind: 'redirect',
        redirectTo: '/configuration/integrations',
      },
    ])
  })

  it('keeps scanning when a nested object appears before path', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  staticData: {
    nested: { deeper: true },
  },
  path: '/nested-before-path',
  component: Page,
})
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([{ path: '/nested-before-path', kind: 'page' }])
  })

  it('ignores braces inside string literals', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/literal-braces',
  meta: { label: 'has { brace' },
})
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([{ path: '/literal-braces', kind: 'page' }])
  })
})

describe('extractBalancedObjectBody', () => {
  it('returns null for unbalanced input', () => {
    expect(extractBalancedObjectBody('{ left open', 0)).toBeNull()
  })
})

describe('parseMountedRouteModules', () => {
  it('requires both import and addChildren spread', () => {
    const treeSource = `
import { rootRoute } from './routes/__root'
import { workflowsRoutes } from './routes/workflows'
import { orphanRoutes } from './routes/orphan'

export const buildTanStackRouteTree = () =>
  rootRoute.addChildren([
    ...workflowsRoutes,
  ])
`
    expect(parseMountedRouteModules(treeSource)).toStrictEqual(['workflows'])
  })
})

describe('collectAppLevelRoutesFromSource', () => {
  it('resolves AppRoute pathname escape hatches', () => {
    const catalog = { Auth: { TestSignInCallback: '/auth/test-signin-callback' } }
    const source = `
      if (globalThis.location.pathname === AppRoute.Auth.TestSignInCallback) {
        return <TestSignInCallback />
      }
    `
    expect(collectAppLevelRoutesFromSource(source, catalog)).toStrictEqual([
      {
        template: '/auth/test-signin-callback',
        parameters: [],
        kind: 'app',
        sources: ['app', 'appRoute'],
      },
    ])
  })

  it('accepts literal pathname comparisons', () => {
    const source = `if (location.pathname === '/custom-app-path') return null`
    expect(collectAppLevelRoutesFromSource(source, {})).toStrictEqual([
      {
        template: '/custom-app-path',
        parameters: [],
        kind: 'app',
        sources: ['app'],
      },
    ])
  })
})

describe('collectFallbackRouteFromSource', () => {
  it('reads the not-found navigate target', () => {
    const source = `
function NotFoundRedirect() {
  useEffect(() => {
    detachPromise(navigate({ to: '/workflows', replace: true }))
  }, [navigate])
  return null
}
`
    expect(collectFallbackRouteFromSource(source)).toStrictEqual({
      template: '*',
      parameters: [],
      kind: 'fallback',
      redirectTo: '/workflows',
      sources: ['router'],
    })
  })

  it('throws when the navigate target is missing', () => {
    expect(() => collectFallbackRouteFromSource('export const rootRoute = {}')).toThrow(/not-found navigate/)
  })
})

describe('collectPathsFromObject', () => {
  it('flattens nested path catalogs', () => {
    const paths = collectPathsFromObject({
      Root: '/workflows',
      Detail: { path: '/workflows/:id' },
    })
    expect([...paths].sort()).toStrictEqual(['/workflows', '/workflows/:id'])
  })
})

describe('collectNavigationPathsFromSource', () => {
  it('resolves AppRoute references and literal paths', () => {
    const catalog = {
      Workflows: { Root: '/workflows' },
      Approvals: { Root: '/approvals' },
    }
    const source = `
      { path: AppRoute.Workflows.Root },
      { path: AppRoute.Approvals.Root },
      { path: '/custom' },
    `
    expect(collectNavigationPathsFromSource(source, catalog)).toStrictEqual(['/approvals', '/custom', '/workflows'])
  })
})

describe('resolveAppRouteReference', () => {
  it('walks dotted AppRoute paths', () => {
    const catalog = { AccessManagement: { Users: '/system-administration/access-management/users' } }
    expect(resolveAppRouteReference(catalog, 'AppRoute.AccessManagement.Users')).toBe(
      '/system-administration/access-management/users'
    )
  })
})

describe('parseAppRouteCatalog', () => {
  it('parses nested AppRoute object literals from source', () => {
    const source = `
export const AppRoute = {
  Workflows: {
    Root: '/workflows',
  },
  Auth: {
    TestSignInCallback: '/auth/test-signin-callback',
  },
}
`
    const catalog = parseAppRouteCatalog(source)
    expect(resolveAppRouteReference(catalog, 'AppRoute.Workflows.Root')).toBe('/workflows')
    expect(resolveAppRouteReference(catalog, 'AppRoute.Auth.TestSignInCallback')).toBe('/auth/test-signin-callback')
  })
})
