import type { Page } from '../fixtures'

type CanIRequestBody = {
  action?: string
  resource_type?: string
  check_any_project?: boolean
  resource_project?: string
}

/**
 * Pin authz responses to a persona's explicit policy actions for this browser page.
 *
 * E2E personas are real users on the backend (or mock users with permissive default
 * can_i). They still inherit grants such as project-user on the authenticated group
 * for created projects, which would show every Tasks tab. Route interception keeps
 * these tests focused on UI gating for the intended action set.
 *
 * Call this before `loginAsUser` (or any navigation that loads the app shell) so
 * TanStack Query does not cache real-backend `can_i` results with `staleTime: Infinity`.
 */
export async function installPersonaAuthzRoutes(page: Page, policyActions: string[]): Promise<void> {
  const allowedKeys = new Set(policyActions.map((a) => a.toLowerCase()))

  const isAllowed = (resourceType: string, action: string): boolean => allowedKeys.has(`${resourceType}:${action}`)

  await page.route('**/api/v1/authz/can_i', async (route) => {
    const body = (route.request().postDataJSON() ?? {}) as CanIRequestBody
    const action = (body.action ?? '').toLowerCase()
    const resourceType = (body.resource_type ?? '').toLowerCase()
    const allowed = Boolean(action && resourceType && isAllowed(resourceType, action))

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        allowed,
        denied: !allowed,
        matched_policy: allowed ? 'persona-policy' : '',
        denial_reason: allowed ? '' : `Insufficient permissions for ${resourceType}:${action}`,
        denied_by: allowed ? '' : 'authorization-service',
      }),
    })
  })

  const whatCanIResources = [
    {
      policy_name: 'persona-policy',
      effect: 'allow',
      actions: policyActions,
      scope: 'any',
      project: '',
    },
  ]

  await page.route('**/api/v1/authz/what_can_i', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        resources: whatCanIResources,
        next: null,
        prev: null,
        total: whatCanIResources.length,
      }),
    })
  })
}
