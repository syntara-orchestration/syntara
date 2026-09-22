import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

/** Boots the mock API the same way `src/index.ts` does, on an ephemeral port. */
let server: Server
let baseUrl: string

beforeAll(async () => {
  const app = createServer(...handlers) as unknown as { listen: (port: number) => Server }
  server = app.listen(0)
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('mock API did not bind a TCP port')
  baseUrl = `http://127.0.0.1:${address.port}`
})

afterAll(async () => {
  await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())))
})

type MockNode = { id: string; type: string; parameters?: Record<string, unknown> }
type MockEdge = { from: string; to: string; from_port?: string }

async function fetchWorkflowByName(name: string) {
  const list = await fetch(`${baseUrl}/api/v1/workflows?limit=100`).then((response) => response.json())
  const summary = list.resources.find((workflow: { name: string }) => workflow.name === name)
  expect(summary, `workflow "${name}" is not seeded`).toBeDefined()
  return fetch(`${baseUrl}/api/v1/workflows/${summary.id}`).then((response) => response.json())
}

describe('node-kind example workflows', () => {
  it('seeds a permission_check example with allowed and denied ports', async () => {
    const workflow = await fetchWorkflowByName('permission-check-routing')
    const definition = workflow.version.workflow_definition

    const check = (definition.nodes as MockNode[]).find((node) => node.type === 'permission_check')
    expect(check).toBeDefined()

    const ports = (definition.edges as MockEdge[])
      .filter((edge) => edge.from === check?.id)
      .map((edge) => edge.from_port)
    expect(ports).toEqual(['allowed', 'denied'])
  })

  it('seeds a permission_check example with exactly one incoming edge on the check', async () => {
    const workflow = await fetchWorkflowByName('permission-check-routing')
    const definition = workflow.version.workflow_definition
    const check = (definition.nodes as MockNode[]).find((node) => node.type === 'permission_check')

    const incoming = (definition.edges as MockEdge[]).filter((edge) => edge.to === check?.id)
    expect(incoming).toHaveLength(1)
  })

  it('seeds an mcp_tool example with integration_id, tool_name and arguments', async () => {
    const workflow = await fetchWorkflowByName('mcp-tool-call')
    const definition = workflow.version.workflow_definition

    const node = (definition.nodes as MockNode[]).find((candidate) => candidate.type === 'mcp_tool')
    expect(node?.parameters).toMatchObject({
      integration_id: expect.any(String) as unknown as string,
      tool_name: 'list_directory',
      timeout_seconds: 30,
    })
    expect(node?.parameters?.arguments).toBeDefined()
  })
})

describe('denied execution fixture', () => {
  it('exposes denied_nodes on the execution', async () => {
    const execution = await fetch(`${baseUrl}/api/v1/executions/exec-denied?include=activities`).then((response) =>
      response.json()
    )

    expect(execution.denied_nodes).toEqual([
      { node_id: 'restart_service', kind: 'http_request', denied_by: 'no-restarts-in-production' },
    ])
  })

  it('includes an activity with the denied status', async () => {
    const execution = await fetch(`${baseUrl}/api/v1/executions/exec-denied?include=activities`).then((response) =>
      response.json()
    )

    const denied = (execution.activities as { activity_id: string; status: string }[]).find(
      (activity) => activity.activity_id === 'restart_service'
    )
    expect(denied?.status).toBe('denied')
  })
})
