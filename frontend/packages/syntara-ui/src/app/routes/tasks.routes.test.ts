import { describe, expect, it } from 'vitest'

import { tasksRoutes } from './tasks'

function getThrownRedirect(beforeLoad: () => void): { options: { to: string; replace: boolean } } {
  try {
    beforeLoad()
  } catch (error) {
    return error as { options: { to: string; replace: boolean } }
  }
  throw new Error('expected beforeLoad to throw a redirect')
}

describe('tasksRoutes', () => {
  const redirectRoute = tasksRoutes[0]
  const tabRoute = tasksRoutes[1]
  const redirectOpts = redirectRoute.options as { path?: string; beforeLoad?: () => void }
  const tabOpts = tabRoute.options as { path?: string }

  it('redirects /tasks to /tasks/approvals with replace', () => {
    expect(redirectOpts.path).toBe('/tasks')
    expect(redirectOpts.beforeLoad).toBeDefined()
    const redirect = getThrownRedirect(redirectOpts.beforeLoad!)
    expect(redirect.options).toMatchObject({
      to: '/tasks/approvals',
      replace: true,
    })
  })

  it('registers /tasks/$tab for the Tasks shell', () => {
    expect(tabOpts.path).toBe('/tasks/$tab')
  })
})
