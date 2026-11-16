/**
 * Mock-API OpenShift (execution plane) seed helpers.
 *
 * Specs that delete or rename the sole mock OpenShift integration should call
 * `restoreOpenShiftSeed` in cleanup so later EP tests still find a singleton.
 *
 * Seed identity is the human-readable fixture name from the mock API — resolve
 * the runtime id via `findOpenShiftSeed` instead of hardcoding UUID literals.
 */
import type { Page } from '../fixtures'
import { apiRequest, getAuthToken } from '../utils/api'

import { deleteIntegrationViaApi } from './resources'

/** Display name of the mock API's sole OpenShift integration fixture. */
export const OPENSHIFT_SEED_NAME = 'prod-openshift-west'

const OPENSHIFT_SEED_BASE_URL = 'https://api.west.openshift.example.com:6443'

type OpenShiftListItem = { id: string; name: string }

async function listOpenShiftIntegrations(app: Page, auth: string): Promise<OpenShiftListItem[]> {
  const listResp = await apiRequest(app, 'get', '/integrations?integration_type=openshift&limit=10', { token: auth })
  if (!listResp.ok()) return []
  const list = (await listResp.json()) as { resources?: OpenShiftListItem[] }
  return list.resources ?? []
}

/** Look up the mock OpenShift seed by fixture name (id comes from the API). */
export async function findOpenShiftSeed(app: Page): Promise<OpenShiftListItem | null> {
  const auth = await getAuthToken(app)
  if (!auth) return null
  const matches = (await listOpenShiftIntegrations(app, auth)).filter((item) => item.name === OPENSHIFT_SEED_NAME)
  return matches[0] ?? null
}

/** Delete non-seed OpenShift integrations and recreate the mock seed if missing. */
export async function restoreOpenShiftSeed(app: Page): Promise<void> {
  const auth = await getAuthToken(app)
  if (!auth) return

  for (const resource of await listOpenShiftIntegrations(app, auth)) {
    if (resource.name !== OPENSHIFT_SEED_NAME) {
      await deleteIntegrationViaApi(app, resource.id)
    }
  }

  const remaining = await listOpenShiftIntegrations(app, auth)
  if (remaining.some((resource) => resource.name === OPENSHIFT_SEED_NAME)) return

  await apiRequest(app, 'post', '/integrations', {
    token: auth,
    data: {
      name: OPENSHIFT_SEED_NAME,
      integration_type: 'openshift',
      configuration: {
        integration_type: 'openshift',
        base_url: OPENSHIFT_SEED_BASE_URL,
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
      scope: 'global',
      management_credential_id: 'cred-001',
    },
  })
}
