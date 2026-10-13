import { describe, expect, it } from 'vitest'

import { approvalsRoutes } from './approvals'

function getThrownRedirect(beforeLoad: () => void): { options: { to: string; replace: boolean } } {
  try {
    beforeLoad()
  } catch (error) {
    return error as { options: { to: string; replace: boolean } }
  }
  throw new Error('expected beforeLoad to throw a redirect')
}

describe('approvalsRoutes', () => {
  const route = approvalsRoutes[0]
  const routeOpts = route.options as { path?: string; beforeLoad?: () => void }

  it('registers /approvals', () => {
    expect(routeOpts.path).toBe('/approvals')
  })

  it('redirects /approvals to /tasks/approvals with replace', () => {
    expect(routeOpts.beforeLoad).toBeDefined()
    const redirect = getThrownRedirect(routeOpts.beforeLoad!)
    expect(redirect.options).toMatchObject({
      to: '/tasks/approvals',
      replace: true,
    })
  })
})
