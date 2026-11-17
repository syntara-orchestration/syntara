/**
 * Mock-API OpenShift (execution plane) seed helpers.
 *
 * Prefer read-only lookups (`findOpenShiftSeed`) from parallel E2E specs. Do not
 * delete the sole OpenShift seed under `fullyParallel` — other workers share one
 * mock API and will observe zero OpenShift integrations (flaky skips/failures).
 * For create-availability UI, use page.route fixture isolation instead.
 *
 * Seed identity is the human-readable fixture name from the mock API — resolve
 * the runtime id via `findOpenShiftSeed` instead of hardcoding UUID literals.
 */
import { IntegrationTypeEnum } from '@syntara/contracts'

import type { Page } from '../fixtures'
import { apiRequest, getAuthToken } from '../utils/api'

/** Display name of the mock API's sole OpenShift integration fixture. */
export const OPENSHIFT_SEED_NAME = 'prod-openshift-west'

type OpenShiftListItem = { id: string; name: string }

function isOpenShiftListItem(value: unknown): value is OpenShiftListItem {
  if (typeof value !== 'object' || value === null) return false
  if (!('id' in value) || !('name' in value)) return false
  return typeof value.id === 'string' && typeof value.name === 'string'
}

/** Narrow untrusted list JSON to `{ id, name }` rows; drop malformed entries. */
function parseOpenShiftListResources(body: unknown): OpenShiftListItem[] {
  if (typeof body !== 'object' || body === null || !('resources' in body)) return []
  const { resources } = body
  if (!Array.isArray(resources)) return []
  return resources.filter(isOpenShiftListItem)
}

/** Look up the mock OpenShift seed by fixture name (id comes from the API). */
export async function findOpenShiftSeed(app: Page): Promise<OpenShiftListItem | null> {
  const auth = await getAuthToken(app)
  if (!auth) return null

  const listResp = await apiRequest(
    app,
    'get',
    `/integrations?integration_type=${IntegrationTypeEnum.OPENSHIFT}&limit=10`,
    { token: auth }
  )
  if (!listResp.ok()) return null

  const body: unknown = await listResp.json()
  const matches = parseOpenShiftListResources(body).filter((item) => item.name === OPENSHIFT_SEED_NAME)
  return matches[0] ?? null
}
