import type {
  AAPAPI,
  AdminAPI,
  ApprovalsAPI,
  AuthAPI,
  CredentialsAPI,
  ExecutionsAPI,
  FilesAPI,
  IdentityProvidersAPI,
  IntegrationsAPI,
  SettingsAPI,
  ToolManagerAPI,
  UsersAPI,
  WorkflowAPI,
} from '@syntara/contracts'
import createFetchClient, { type Middleware } from 'openapi-fetch'
import createClient from 'openapi-react-query'

import { useAuthStore } from './stores/useAuthStore'
import { backendOrigin } from './utils/backendUrl'
import { applyOrchestratorUiClientHeader } from './utils/orchestratorClientHeader'

// ============================================================================
// Interface Tagging Middleware
// ============================================================================

/**
 * openapi-fetch middleware that tags every request with `X-Orchestrator-Client: ui`
 * so the backend can distinguish UI traffic from external API consumers
 * (CLI, CI/CD, scripts) in metrics and telemetry.
 */
const interfaceTagMiddleware: Middleware = {
  onRequest({ request }) {
    applyOrchestratorUiClientHeader(request.headers)
    return request
  },
}

// ============================================================================
// Auth Middleware
// ============================================================================

/**
 * openapi-fetch middleware that:
 * 1. Ensures a valid access token before every request (refreshing if needed)
 * 2. Injects the Authorization header
 * 3. On 401 response: attempts a single refresh then retries the request
 */
const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const store = useAuthStore.getState()

    try {
      await store.ensureValidToken()
    } catch {
      // If we can't get a valid token, let the request proceed without auth
      // The server will return 401 and onResponse will handle it
      return request
    }

    const { accessToken } = useAuthStore.getState()
    if (accessToken) {
      request.headers.set('Authorization', `Bearer ${accessToken}`)
    }

    return request
  },

  async onResponse({ request, response }) {
    if (response.status !== 401) {
      return response
    }

    // Prevent infinite retry loops: if this is already a retried request, return the 401 directly
    if (request.headers.get('X-Auth-Retry') === '1') {
      return response
    }

    // Attempt one refresh
    const store = useAuthStore.getState()
    try {
      await store.refresh()
    } catch {
      // Refresh failed — clear auth state
      store.clearAuth()
      return response
    }

    const { accessToken } = useAuthStore.getState()
    if (!accessToken) {
      return response
    }

    // Retry the original request with the new token
    const retryRequest = new Request(request, {
      headers: new Headers(request.headers),
    })
    retryRequest.headers.set('Authorization', `Bearer ${accessToken}`)
    retryRequest.headers.set('X-Auth-Retry', '1')
    // eslint-disable-next-line syntara/no-raw-http-calls -- auth middleware retry with refreshed token after 401
    return fetch(retryRequest)
  },
}

// Exported for testing
export { authMiddleware, interfaceTagMiddleware }

// ============================================================================
// API Clients
// ============================================================================

const workflowFetchClient = createFetchClient<WorkflowAPI.paths>({ baseUrl: '/api/v1/' })
workflowFetchClient.use(interfaceTagMiddleware)
workflowFetchClient.use(authMiddleware)
export { workflowFetchClient }
export const workflowClient = createClient(workflowFetchClient)

export const executionsFetchClient = createFetchClient<ExecutionsAPI.paths>({ baseUrl: '/api/v1/' })
executionsFetchClient.use(interfaceTagMiddleware)
executionsFetchClient.use(authMiddleware)
export const executionsClient = createClient(executionsFetchClient)

export const toolManagerFetchClient = createFetchClient<ToolManagerAPI.paths>({ baseUrl: '/api/v1/' })
toolManagerFetchClient.use(interfaceTagMiddleware)
toolManagerFetchClient.use(authMiddleware)
export const toolManagerClient = createClient(toolManagerFetchClient)

const approvalsFetchClient = createFetchClient<ApprovalsAPI.paths>({ baseUrl: '/api/v1/' })
approvalsFetchClient.use(interfaceTagMiddleware)
approvalsFetchClient.use(authMiddleware)
export const approvalsClient = createClient(approvalsFetchClient)

const settingsFetchClient = createFetchClient<SettingsAPI.paths>({ baseUrl: '/api/v1/' })
settingsFetchClient.use(interfaceTagMiddleware)
settingsFetchClient.use(authMiddleware)
export { settingsFetchClient }
export const settingsClient = createClient(settingsFetchClient)

// integrationsFetchClient is exported for use in components that call the API directly inside
// useQueries queryFn callbacks, where hooks (integrationsClient.useQuery) cannot be used.
export const integrationsFetchClient = createFetchClient<IntegrationsAPI.paths>({ baseUrl: '/api/v1/' })
integrationsFetchClient.use(interfaceTagMiddleware)
integrationsFetchClient.use(authMiddleware)
export const integrationsClient = createClient(integrationsFetchClient)

const identityProvidersFetchClient = createFetchClient<IdentityProvidersAPI.paths>({
  baseUrl: '/api/v1',
})
identityProvidersFetchClient.use(interfaceTagMiddleware)
identityProvidersFetchClient.use(authMiddleware)
export const identityProvidersClient = createClient(identityProvidersFetchClient)

export const authFetchClient = createFetchClient<AuthAPI.paths>({ baseUrl: '/api/v1' })
authFetchClient.use(interfaceTagMiddleware)
authFetchClient.use(authMiddleware)
export const authClient = createClient(authFetchClient)

/**
 * OIDC redirect URLs — full-page navigations handled by the backend, not JSON API calls.
 * These are not in the OpenAPI contract because the browser navigates to them directly.
 */
export const OIDC_REDIRECT_URI = `${backendOrigin}/api/v1/auth/oidc/callback`
export const OIDC_AUTHORIZE_PATH = '/api/v1/auth/oidc/authorize'

// SECURITY NOTE: These fetch clients include authentication middleware (authMiddleware)
// which automatically attaches the auth token from localStorage. They are exported
// for use in other modules that need direct fetch access (e.g., file downloads).
// All API calls should use the typed query/mutation clients (e.g., usersClient)
// rather than the raw fetchClient to ensure type safety and proper error handling.
export const usersFetchClient = createFetchClient<UsersAPI.paths>({ baseUrl: '/api/v1' })
usersFetchClient.use(interfaceTagMiddleware)
usersFetchClient.use(authMiddleware)
export const usersClient = createClient(usersFetchClient)

const credentialsFetchClient = createFetchClient<CredentialsAPI.paths>({ baseUrl: '/api/v1/' })
credentialsFetchClient.use(interfaceTagMiddleware)
credentialsFetchClient.use(authMiddleware)
export const credentialsClient = createClient(credentialsFetchClient)

const aapFetchClient = createFetchClient<AAPAPI.paths>({ baseUrl: '/api/v1/' })
aapFetchClient.use(interfaceTagMiddleware)
aapFetchClient.use(authMiddleware)
export const aapClient = createClient(aapFetchClient)

const adminFetchClient = createFetchClient<AdminAPI.paths>({ baseUrl: '/api/v1/' })
adminFetchClient.use(interfaceTagMiddleware)
adminFetchClient.use(authMiddleware)
export const adminClient = createClient(adminFetchClient)

export const filesFetchClient = createFetchClient<FilesAPI.paths>({ baseUrl: '/api/v1/' })
filesFetchClient.use(interfaceTagMiddleware)
filesFetchClient.use(authMiddleware)
export const filesClient = createClient(filesFetchClient)
