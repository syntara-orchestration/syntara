import { type Response } from '@playwright/test'

import { expect, appBaseUrl, type Page } from '../fixtures'
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

/** Creates an execution target via the facade API. Caller must delete the returned id. */
export async function createExecutionTargetViaApi(
  app: Page,
  input: { name: string; namespace?: string }
): Promise<{ id: string; name: string }> {
  const token = await getAuthToken(app)
  if (!token) {
    throw new Error('Missing auth token; cannot create execution target via API')
  }

  const url = new URL('/api/execution_plane/v1/execution_targets', appBaseUrl).toString()
  const response = await app.request.post(url, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: input.name,
      placement: {
        type: 'kubernetes',
        namespace: input.namespace ?? 'aao-execution',
        node_selectors: [],
      },
    },
  })

  if (!response.ok()) {
    throw new Error(`Failed to create execution target via API: ${String(response.status())} ${await response.text()}`)
  }

  const body = (await response.json()) as { id?: string; name?: string }
  if (!body.id) {
    throw new Error('Create execution target response missing id')
  }

  return { id: body.id, name: body.name ?? input.name }
}

/** Best-effort DELETE for E2E cleanup. */
export async function deleteExecutionTargetViaApi(app: Page, targetId: string): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) return

  const url = new URL(`/api/execution_plane/v1/execution_targets/${targetId}`, appBaseUrl).toString()
  await app.request.delete(url, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
}

/** PATCH enable/disable for setup between UI assertions. */
export async function patchExecutionTargetEnabledViaApi(app: Page, targetId: string, enabled: boolean): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) {
    throw new Error('Missing auth token; cannot patch execution target via API')
  }

  const url = new URL(`/api/execution_plane/v1/execution_targets/${targetId}`, appBaseUrl).toString()
  const response = await app.request.patch(url, {
    headers: { Authorization: `Bearer ${token}` },
    data: { enabled },
  })

  if (!response.ok()) {
    throw new Error(
      `Failed to patch execution target enabled=${String(enabled)}: ${String(response.status())} ${await response.text()}`
    )
  }
}

/** The PATCH that the Enabled switch issues. */
export function isExecutionTargetPatchResponse(response: Response): boolean {
  return (
    response.request().method() === 'PATCH' &&
    /\/api\/execution_plane\/v1\/execution_targets\/[^/]+$/.test(new URL(response.url()).pathname)
  )
}

/** Per-attempt budget for the enable/disable PATCH to come back. */
export const EXECUTION_TARGET_PATCH_TIMEOUT = 20_000

/**
 * Confirm the disable dialog and wait for a successful PATCH.
 * Armed before the confirm click so optimistic UI alone cannot race past the server write.
 */
export async function confirmDisableExecutionTarget(app: Page): Promise<void> {
  const dialog = app.getByRole('dialog')
  await expect(dialog.getByText('Disable execution target?')).toBeVisible()
  await expect(dialog.getByText(/This will immediately:/i)).toBeVisible()

  const patchDone = app.waitForResponse(isExecutionTargetPatchResponse, {
    timeout: EXECUTION_TARGET_PATCH_TIMEOUT,
  })
  await dialog.getByRole('button', { name: 'Disable' }).click()

  const response = await patchDone
  expect(response.ok(), `PATCH execution target returned ${String(response.status())}`).toBe(true)
  await expect(dialog).not.toBeVisible()
}
