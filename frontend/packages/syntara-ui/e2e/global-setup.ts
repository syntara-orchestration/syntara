/**
 * Playwright globalSetup — probes backend service health once before all tests.
 *
 * On a real backend (NEXUS_E2E_SKIP_WEB_SERVER=1), this creates a throwaway
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
 * polling a minimal workflow.
 *
 * Returns which services are **positively confirmed as down**. A timeout or
 * error is treated as inconclusive (fail-open).
 */
async function probeExecutionEngine(token: string): Promise<{
  executionEngineDown: boolean
  temporalWorkerDown: boolean
}> {
  const result = { executionEngineDown: false, temporalWorkerDown: false }
  let createdProjectId: string | null = null

  try {
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
      createdProjectId = projectId
    }

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
      await api(token, 'POST', `/workflows/${workflowId}/versions/${workflow.current_version}/publish`, {})

      const runResp = await api(token, 'POST', `/workflows/${workflowId}/run`, {})
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
        const statusResp = await api(token, 'GET', `/executions/${executionId}`)
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
      await api(token, 'DELETE', `/workflows/${workflowId}`).catch(() => {})
    }
  } catch {
    // Network/unexpected error — inconclusive, leave fail-open defaults
  } finally {
    if (createdProjectId) {
      await api(token, 'DELETE', `/projects/${createdProjectId}`).catch(() => {})
    }
  }

  return result
}

export default async function globalSetup(): Promise<void> {
  // Default to healthy — tests run unless probe positively confirms otherwise
  process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE'] = '1'
  process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER'] = '1'

  if (!isSkipWebServerForPlaywrightTests()) return

  console.log('[global-setup] Probing backend service health...')

  const token = await authenticate()
  if (!token) {
    console.log('[global-setup] Could not authenticate — assuming services are healthy (fail-open)')
    return
  }

  const { executionEngineDown, temporalWorkerDown } = await probeExecutionEngine(token)

  if (executionEngineDown) {
    delete process.env['SYNTARA_E2E_HAS_EXECUTION_ENGINE']
    delete process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']
  } else if (temporalWorkerDown) {
    delete process.env['SYNTARA_E2E_HAS_TEMPORAL_WORKER']
  }

  console.log(
    `[global-setup] Probe results: execution_engine=${!executionEngineDown}, temporal_worker=${!temporalWorkerDown}`
  )
}
