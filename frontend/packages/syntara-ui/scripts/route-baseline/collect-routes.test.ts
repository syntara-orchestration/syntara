import { describe, expect, it } from 'vitest'

import {
  collectAppLevelRoutesFromSource,
  collectFallbackRouteFromSource,
  collectNavigationPathsFromSource,
  collectPathsFromObject,
  extractBalancedObjectBody,
  parseAppRouteCatalog,
  parseCreateRouteBlocks as parseBlocks,
  resolveAppRouteReference,
} from './collect-routes'

// Each parser fixture includes a real root declaration; unresolved parents must fail.
function parseCreateRouteBlocks(source: string, options?: Parameters<typeof parseBlocks>[1]) {
  return parseBlocks(`const rootRoute = createRootRoute({})\n${source}`, options)
}

describe('parseCreateRouteBlocks', () => {
  it('ignores route-like comments, strings and nested metadata paths', () => {
    const source = `
const example = "createRoute({ path: '/example' })"
// createRoute({ path: '/comment' })
createRoute({
  getParentRoute: () => rootRoute,
  staticData: { path: '/metadata' },
  path: '/actual',
})
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([{ path: '/actual', kind: 'page' }])
  })

  it('resolves nested child paths even when the parent is declared later', () => {
    const source = `
const fieldRoute = createRoute({ getParentRoute: () => categoryRoute, path: '/$field' })
const categoryRoute = createRoute({ getParentRoute: () => settingsRoute, path: '/$category' })
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/system-administration/settings' })
`
    expect(parseCreateRouteBlocks(source)).toStrictEqual([
      { path: '/system-administration/settings/$category/$field', kind: 'page' },
      { path: '/system-administration/settings/$category', kind: 'page' },
      { path: '/system-administration/settings', kind: 'page' },
    ])
  })

  it('rejects cyclic route parents instead of overflowing the stack', () => {
    const source = `
const firstRoute = createRoute({ getParentRoute: () => secondRoute, path: '/first' })
const secondRoute = createRoute({ getParentRoute: () => firstRoute, path: '/second' })
`
    expect(() => parseCreateRouteBlocks(source)).toThrow('Cyclic route parent reference')
  })

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

  it('resolves redirect({ to: AppRoute... }) against the catalog', () => {
    const catalog = {
      Configuration: {
        Credentials: { Root: '/configuration/credentials' },
      },
    }
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: AppRoute.Configuration.Credentials.Root, replace: true }),
})
`
    expect(parseCreateRouteBlocks(source, { appRouteCatalog: catalog })).toStrictEqual([
      {
        path: '/configuration',
        kind: 'redirect',
        redirectTo: '/configuration/credentials',
      },
    ])
  })

  it('throws when AppRoute redirect cannot be resolved', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: AppRoute.Missing.Path, replace: true }),
})
`
    expect(() => parseCreateRouteBlocks(source, { appRouteCatalog: {} })).toThrow(
      /Could not resolve redirect target AppRoute\.Missing\.Path/
    )
  })

  it('throws for unsupported non-literal redirect targets', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: someVariable, replace: true }),
})
`
    expect(() => parseCreateRouteBlocks(source)).toThrow(/Unsupported redirect/)
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
