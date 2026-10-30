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

type CreateExecutionTargetBody = {
  name: string
  namespace?: string
  is_default?: boolean
}

type CreatedExecutionTarget = {
  id: string
  name: string
}

/** Create an execution target via the facade POST (for self-contained E2E cleanup). */
export async function createExecutionTargetViaApi(
  app: Page,
  body: CreateExecutionTargetBody
): Promise<CreatedExecutionTarget | null> {
  const token = await getAuthToken(app)
  if (!token) return null

  const url = new URL('/api/execution_plane/v1/execution_targets', appBaseUrl).toString()
  const response = await app.request.post(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: {
      name: body.name,
      placement: {
        type: 'kubernetes',
        namespace: body.namespace ?? 'e2e-execution',
        node_selectors: [],
        tolerations: [],
      },
      is_default: body.is_default ?? false,
    },
  })
  if (!response.ok()) return null
  const json = (await response.json()) as { id?: string; name?: string }
  if (!json.id || !json.name) return null
  return { id: json.id, name: json.name }
}

/** Best-effort DELETE for E2E cleanup. */
export async function deleteExecutionTargetViaApi(app: Page, targetId: string): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) return

  const url = new URL(`/api/execution_plane/v1/execution_targets/${targetId}`, appBaseUrl).toString()
  await app.request.delete(url, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
}
