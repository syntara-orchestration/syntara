/**
 * Credential API helpers for E2E test setup/teardown.
 */
import type { Page } from '../fixtures'

import { apiRequest, getAuthToken } from './api-core'

/**
 * Create a credential via the API. Returns the credential ID or null.
 */
export async function createCredentialViaApi(
  app: Page,
  options: { name: string; projectId: string; typeId?: string }
): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null

    const typesResp = await apiRequest(app, 'get', '/credential_types', { token })
    if (!typesResp.ok()) return null

    const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
    const targetType =
      options.typeId ?? types.resources?.find((t) => t.name.includes('Bearer'))?.id ?? types.resources?.[0]?.id
    if (!targetType) return null

    const createResp = await apiRequest(app, 'post', '/credentials', {
      token,
      data: {
        name: options.name,
        credential_type_id: targetType,
        project_id: options.projectId,
        inputs: { token: 'e2e-test-token' },
      },
    })
    if (!createResp.ok()) return null
    const cred = (await createResp.json()) as { id?: string }
    return cred.id ?? null
  } catch {
    return null
  }
}

/**
 * Delete a credential via the API (best-effort cleanup).
 */
export async function deleteCredentialViaApi(app: Page, credentialId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) {
      await apiRequest(app, 'delete', `/credentials/${credentialId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

type CredentialSummary = { id: string; name: string; project_id?: string }

function pickCredentialInProject(
  resources: CredentialSummary[] | undefined,
  name: string,
  projectId: string
): CredentialSummary | null {
  return resources?.find((c) => c.name === name && c.project_id === projectId) ?? null
}

/**
 * Find a credential by exact name within a project (idempotent E2E setup).
 *
 * Uses `name[eq]` on the real backend; falls back to mock API `name=` exact filter.
 */
export async function findCredentialByNameAndProject(
  app: Page,
  name: string,
  projectId: string
): Promise<{ id: string; name: string } | null> {
  const queries = [`name[eq]=${encodeURIComponent(name)}&limit=100`, `name=${encodeURIComponent(name)}&limit=100`]

  for (const query of queries) {
    const resp = await apiRequest(app, 'get', `/credentials?${query}`)
    if (!resp.ok()) continue
    const body = (await resp.json()) as { resources?: CredentialSummary[] }
    const match = pickCredentialInProject(body.resources, name, projectId)
    if (match) return { id: match.id, name: match.name }
  }

  return null
}

/**
 * List credentials by name via the authenticated API.
 * Returns matching credentials for cleanup purposes.
 */
export async function listCredentialsByName(app: Page, name: string): Promise<Array<{ id: string }>> {
  try {
    const token = await getAuthToken(app)
    if (!token) return []

    const resp = await apiRequest(app, 'get', `/credentials?name[eq]=${encodeURIComponent(name)}&limit=100`, {
      token,
    })
    if (!resp.ok()) {
      const fallback = await apiRequest(app, 'get', `/credentials?name=${encodeURIComponent(name)}&limit=100`, {
        token,
      })
      if (!fallback.ok()) return []
      const fallbackBody = (await fallback.json()) as { resources?: Array<{ id: string }> }
      return fallbackBody.resources ?? []
    }

    const body = (await resp.json()) as { resources?: Array<{ id: string }> }
    return body.resources ?? []
  } catch {
    return []
  }
}
