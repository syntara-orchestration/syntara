import { appBaseUrl, type Page } from '../fixtures'
import { getAuthToken } from '../utils/api'

/**
 * True when the Execution Plane facade list endpoint is reachable.
 *
 * Compose CI starts Syntara without execution-plane-api, so list/create UI
 * shows an error state instead of the toolbar/empty CTA these E2E tests need.
 */
export async function isExecutionPlaneListReachable(app: Page): Promise<boolean> {
  const token = await getAuthToken(app)
  if (!token) return false

  try {
    const url = new URL('/api/execution_plane/v1/execution_targets?limit=1', appBaseUrl).toString()
    const response = await app.request.get(url, { headers: { Authorization: `Bearer ${token}` } })
    return response.ok()
  } catch {
    return false
  }
}

/** True when exactly one OpenShift integration exists (create form cluster binding). */
export async function hasSingleOpenShiftIntegration(app: Page): Promise<boolean> {
  const token = await getAuthToken(app)
  if (!token) return false

  try {
    const url = new URL(
      '/api/v1/integrations?integration_type=openshift&limit=2&include_total=true',
      appBaseUrl
    ).toString()
    const response = await app.request.get(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok()) return false
    const body = (await response.json()) as { resources?: unknown[]; total?: number }
    const count = body.total ?? body.resources?.length ?? 0
    return count === 1
  } catch {
    return false
  }
}
