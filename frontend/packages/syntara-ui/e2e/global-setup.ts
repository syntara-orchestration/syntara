/**
 * Playwright globalSetup — probes backend service health once before all tests.
 *
 * On a real backend (NEXUS_E2E_SKIP_WEB_SERVER=1), this creates a throwaway
 * workflow, runs it, and checks whether the execution engine and Temporal worker
 * are operational. Results are exported as environment variables so test files
 * can skip entire describe blocks at collection time (0ms cost).
 *
 * On the mock backend this is a no-op — all services are synthetic.
 */
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'

const appBaseUrl: string = process.env['NEXUS_E2E_BASE_URL'] ?? 'http://localhost:4173'

function apiUrl(path: string): string {
  return new URL(`/api/v1${path}`, appBaseUrl).toString()
}

async function authenticate(): Promise<string | null> {
  const password = process.env['NEXUS_E2E_PASSWORD']
  if (!password) return null

  try {
    const resp = await fetch(apiUrl('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password }),
    })
    if (!resp.ok) return null
    const body = (await resp.json()) as { access_token?: string }
    return body.access_token ?? null
  } catch {
    return null
  }
}

async function api(
  token: string,
  method: string,
  path: string,
  data?: unknown
): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }> {
  const resp = await fetch(apiUrl(path), {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
  })
  return { ok: resp.ok, status: resp.status, json: () => resp.json() }
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Probe the execution engine and Temporal worker by creating, running, and
 * polling a minimal workflow. Returns which capabilities are available.
 */
async function probeExecutionEngine(token: string): Promise<{
  executionEngine: boolean
  temporalWorker: boolean
}> {
  const result = { executionEngine: false, temporalWorker: false }

  try {
    // Find or create a project
    const projectsResp = await api(token, 'GET', '/projects')
    if (!projectsResp.ok) return result
    const projects = (await projectsResp.json()) as { resources: Array<{ id: string }> }
    let projectId = projects.resources?.[0]?.id

    if (!projectId) {
      const createProject = await api(token, 'POST', '/projects', {
        name: 'e2e-probe',
        description: 'Health probe project',
      })
      if (!createProject.ok) return result
      projectId = ((await createProject.json()) as { id: string }).id
    }

    // Create a minimal workflow
    const createResp = await api(token, 'POST', '/workflows', {
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
      // Publish
      await api(token, 'POST', `/workflows/${workflowId}/versions/${workflow.current_version}/publish`, {})

      // Run
      const runResp = await api(token, 'POST', `/workflows/${workflowId}/run`, {})
      if (!runResp.ok) return result
      const execution = (await runResp.json()) as { id?: string; execution_id?: string }
      const executionId = execution.id ?? execution.execution_id
      if (!executionId) return result

      result.executionEngine = true

      // Poll execution status — check if Temporal picks it up
      for (let i = 0; i < 15; i++) {
        await sleep(2000)
        const statusResp = await api(token, 'GET', `/executions/${executionId}`)
        if (!statusResp.ok) break
        const exec = (await statusResp.json()) as { status: string }
        if (exec.status !== 'pending') {
          result.temporalWorker = true
          break
        }
      }
    } finally {
      // Clean up
      await api(token, 'DELETE', `/workflows/${workflowId}`).catch(() => {})
    }
  } catch {
    // Probe failed — leave defaults (false)
  }

  return result
}

// eslint-disable-next-line no-restricted-exports -- Playwright requires globalSetup to be a default export
export default async function globalSetup(): Promise<void> {
  if (!isSkipWebServerForPlaywrightTests()) return

  // eslint-disable-next-line no-console -- globalSetup runs in Node before tests; console is the only logging mechanism
  console.log('[global-setup] Probing backend service health...')

  const token = await authenticate()
  if (!token) {
    // eslint-disable-next-line no-console
    console.log('[global-setup] Could not authenticate — skipping probes')
    return
  }

  const { executionEngine, temporalWorker } = await probeExecutionEngine(token)

  if (executionEngine) process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'] = '1'
  if (temporalWorker) process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'] = '1'

  // eslint-disable-next-line no-console
  console.log(`[global-setup] Probe results: execution_engine=${executionEngine}, temporal_worker=${temporalWorker}`)
}
