import { describe, expect, it } from 'vitest'

import {
  collectAppLevelRoutesFromSource,
  collectFallbackRouteFromSource,
  collectNavigationPathsFromSource,
  extractBalancedObjectBody,
  parseCreateRouteBlocks as parseBlocks,
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

  it('resolves route-reference redirects against exported route paths', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: routeRefs.credentialsRoute.fullPath, replace: true }),
})
`
    expect(
      parseCreateRouteBlocks(source, { routeReferencePaths: { credentialsRoute: '/configuration/credentials' } })
    ).toStrictEqual([
      {
        path: '/configuration',
        kind: 'redirect',
        redirectTo: '/configuration/credentials',
      },
    ])
  })

  it('throws when a route-reference redirect cannot be resolved', () => {
    const source = `
createRoute({
  getParentRoute: () => rootRoute,
  path: '/configuration',
  beforeLoad: () => redirect({ to: routeRefs.missingRoute.fullPath, replace: true }),
})
`
    expect(() => parseCreateRouteBlocks(source, { routeReferencePaths: {} })).toThrow(
      /Could not resolve routeRefs\.missingRoute/
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
  it('resolves the app-level callback path definition', () => {
    const source = `
      if (globalThis.location.pathname === testSignInCallbackPath) {
        return <TestSignInCallback />
      }
    `
    const pathSource = `export const testSignInCallbackPath = '/auth/test-signin-callback'`
    expect(collectAppLevelRoutesFromSource(source, pathSource)).toStrictEqual([
      {
        template: '/auth/test-signin-callback',
        parameters: [],
        kind: 'app',
        sources: ['app'],
      },
    ])
  })

  it('ignores path literals outside the app-level path definition', () => {
    const source = `if (location.pathname === '/custom-app-path') return null`
    expect(collectAppLevelRoutesFromSource(source, '')).toStrictEqual([])
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

describe('collectNavigationPathsFromSource', () => {
  it('resolves route references used by navigation items', () => {
    const paths = { workflowsRoute: '/workflows', approvalsRoute: '/approvals' }
    const source = `
      { destination: { to: routeRefs.workflowsRoute.fullPath }, matchPath: routeRefs.workflowsRoute.fullPath },
      { destination: { to: routeRefs.approvalsRoute.fullPath }, matchPath: routeRefs.approvalsRoute.fullPath },
    `
    expect(collectNavigationPathsFromSource(source, paths)).toStrictEqual(['/approvals', '/workflows'])
  })

  it('reports unresolved route references with their source line', () => {
    expect(() =>
      collectNavigationPathsFromSource('{ destination: { to: routeRefs.missingRoute.fullPath } }', {})
    ).toThrow(/routeRefs\.missingRoute\.fullPath in navigationItems\.tsx:1/)
  })
})
