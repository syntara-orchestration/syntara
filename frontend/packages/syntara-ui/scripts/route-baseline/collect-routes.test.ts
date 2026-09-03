import { describe, expect, it } from 'vitest'

import {
  collectPathsFromObject,
  collectNavigationPathsFromSource,
  parseCreateRouteBlocks,
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
    expect(collectNavigationPathsFromSource(source, catalog)).toStrictEqual([
      '/approvals',
      '/custom',
      '/workflows',
    ])
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
