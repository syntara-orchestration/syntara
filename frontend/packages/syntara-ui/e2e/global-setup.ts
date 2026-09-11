/**
 * Playwright globalSetup — probes backend service health once before all tests.
 *
 * On a real backend (SYNTARA_E2E_SKIP_WEB_SERVER=1), this creates a throwaway
 * workflow, runs it, and checks whether the execution engine and Temporal worker
 * are operational. Results are exported as environment variables so test files
 * can skip entire describe blocks at collection time (0ms cost).
 *
 * The probe is **fail-open**: env vars default to '1' (healthy). Only a positive
 * confirmation that a service is down (API responded but execution never left
 * "pending") clears the flag. Timeouts, auth failures, and network errors all
 * leave the flags set so tests run and discover issues themselves.
 *
 * On the mock backend the flags are set to '1' unconditionally — all services
 * are synthetic and always available.
 */
import { request as playwrightRequest, type APIRequestContext } from '@playwright/test'

import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'
import { formatXfailRules, loadXfailEntries, xfailSourceFromEnv } from './xfailFromUrl'

const appBaseUrl: string = process.env['SYNTARA_E2E_BASE_URL'] ?? 'http://localhost:4173'

function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, appBaseUrl).toString()
}

// Playwright's request context is used instead of bare Node.js fetch() so that
// ignoreHTTPSErrors applies — plain fetch() rejects self-signed / cluster-issued
// certs that Playwright browser contexts skip via the ignoreHTTPSErrors config.
async function createContext(): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: appBaseUrl,
    ignoreHTTPSErrors: true,
  })
}

async function authenticate(ctx: APIRequestContext): Promise<string | null> {
  const password = process.env['SYNTARA_E2E_PASSWORD']
  if (!password) return null

  try {
    const resp = await ctx.post(apiUrl('/auth/login'), {
      data: { username: 'admin', password },
    })
    if (!resp.ok()) return null
    const body = (await resp.json()) as { access_token?: string }
    return body.access_token ?? null
  } catch {
    return null
  }
}

async function api(
  ctx: APIRequestContext,
  token: string,
  method: string,
  path: string,
  data?: unknown
): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }> {
  const resp = await ctx.fetch(apiUrl(path), {
    method,
    headers: { Authorization: `Bearer ${token}` },
    ...(data !== undefined && { data }),
  })
  const body: unknown = await resp.json()
  return { ok: resp.ok(), status: resp.status(), json: () => Promise.resolve(body) }
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Probe the execution engine and Temporal worker by creating, running, and
 * polling a minimal workflow.
 *
 * Returns which services are **positively confirmed as down**. A timeout or
 * error is treated as inconclusive (fail-open).
 */
async function probeExecutionEngine(
  ctx: APIRequestContext,
  token: string
): Promise<{
  executionEngineDown: boolean
  temporalWorkerDown: boolean
}> {
  const result = { executionEngineDown: false, temporalWorkerDown: false }
  let createdProjectId: string | null = null

  try {
    const projectsResp = await api(ctx, token, 'GET', '/projects')
    if (!projectsResp.ok) return result
    const projects = (await projectsResp.json()) as { resources: Array<{ id: string }> }
    let projectId = projects.resources?.[0]?.id

    if (!projectId) {
      const createProject = await api(ctx, token, 'POST', '/projects', {
        name: 'e2e-probe',
        description: 'Health probe project',
      })
      if (!createProject.ok) return result
      projectId = ((await createProject.json()) as { id: string }).id
      createdProjectId = projectId
    }

    const createResp = await api(ctx, token, 'POST', '/workflows', {
      name: `__e2e_probe_${Date.now()}`,
      project_id: projectId,
      workflow_definition: {
        schema_version: '2.0.0',
        name: '__e2e_probe',
        triggers: [{ id: 't1', type: 'manual_trigger', name: 'Probe trigger', parameters: {} }],
        nodes: [
          {
            id: 'n1',
            type: 'script',
            name: 'Probe script',
            parameters: { language: 'python', code: 'print("probe")' },
          },
        ],
        edges: [{ from: 't1', to: 'n1' }],
      },
    })
    if (!createResp.ok) return result
    const workflow = (await createResp.json()) as { id: string; current_version: number }
    const workflowId = workflow.id

    try {
      await api(ctx, token, 'POST', `/workflows/${workflowId}/versions/${workflow.current_version}/publish`, {})

      const runResp = await api(ctx, token, 'POST', `/workflows/${workflowId}/run`, {})
      if (!runResp.ok) {
        // API explicitly rejected the run request — engine is positively down
        result.executionEngineDown = true
        return result
      }

      const execution = (await runResp.json()) as { id?: string; execution_id?: string }
      const executionId = execution.id ?? execution.execution_id
      if (!executionId) return result

      // Poll execution status — check if Temporal picks it up
      // Use a longer window (60s) to tolerate Temporal warm-up in Compose
      let finalStatus = 'pending'
      for (let i = 0; i < 30; i++) {
        await sleep(2000)
        const statusResp = await api(ctx, token, 'GET', `/executions/${executionId}`)
        if (!statusResp.ok) return result
        const exec = (await statusResp.json()) as { status: string }
        finalStatus = exec.status
        if (finalStatus !== 'pending') break
      }

      if (finalStatus === 'pending') {
        // Execution stayed pending for the full 60s — Temporal is positively not processing
        result.temporalWorkerDown = true
      }
    } finally {
      await api(ctx, token, 'DELETE', `/workflows/${workflowId}`).catch(() => {})
    }
  } catch {
    // Network/unexpected error — inconclusive, leave fail-open defaults
  } finally {
    if (createdProjectId) {
      await api(ctx, token, 'DELETE', `/projects/${createdProjectId}`).catch(() => {})
    }
  }

  return result
}

/** Print the active xfail rules once, at the very start of the run. */
async function logXfailRules(): Promise<void> {
  const source = xfailSourceFromEnv()
  if (!source) return

  const entries = await loadXfailEntries(source)
  for (const line of formatXfailRules(entries, source)) {
    console.log(`[global-setup] ${line}`)
  }
}

export default async function globalSetup(): Promise<void> {
  await logXfailRules()

  // Default to healthy — tests run unless probe positively confirms otherwise
  process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'] = '1'
  process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'] = '1'

  if (!isSkipWebServerForPlaywrightTests()) return

  console.log('[global-setup] Probing backend service health...')

  const ctx = await createContext()
  try {
    const token = await authenticate(ctx)
    if (!token) {
      console.log('[global-setup] Could not authenticate — assuming services are healthy (fail-open)')
      return
    }

    const { executionEngineDown, temporalWorkerDown } = await probeExecutionEngine(ctx, token)

    if (executionEngineDown) {
      delete process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE']
      delete process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']
    } else if (temporalWorkerDown) {
      delete process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']
    }

    console.log(
      `[global-setup] Probe results: execution_engine=${!executionEngineDown}, temporal_worker=${!temporalWorkerDown}`
    )
  } finally {
    await ctx.dispose()
  }
}
